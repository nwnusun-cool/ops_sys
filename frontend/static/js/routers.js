/**
 * 路由管理页面JavaScript
 */

let currentClusterId = null;
let routersData = [];
let currentPage = 1;
let totalPages = 1;
let selectedRouters = new Set();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('Routers page loaded');
    loadClusters();
    setupEventListeners();
});

// 设置事件监听器
function setupEventListeners() {
    // 过滤表单提交
    document.getElementById('filterForm').addEventListener('submit', function(e) {
        e.preventDefault();
        applyFilters();
    });
    
    // 创建路由器表单提交
    document.getElementById('createRouterForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitCreateRouter();
    });
    
    // 搜索输入框回车
    document.getElementById('searchInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            applyFilters();
        }
    });
}

// 加载集群列表
async function loadClusters() {
    try {
        const response = await fetch('/api/clusters');
        const data = await response.json();
        
        if (data.success) {
            const select = document.getElementById('clusterSelect');
            select.innerHTML = '<option value="">请选择集群</option>';
            
            let firstConnectedCluster = null;
            
            data.data.forEach(cluster => {
                const option = document.createElement('option');
                option.value = cluster.id;
                option.textContent = `${cluster.name} (${cluster.connection_status})`;
                if (cluster.connection_status !== 'connected') {
                    option.disabled = true;
                    option.textContent += ' - 连接失败';
                } else if (!firstConnectedCluster) {
                    firstConnectedCluster = cluster;
                }
                select.appendChild(option);
            });
            
            // 自动选择第一个可用集群
            if (firstConnectedCluster) {
                select.value = firstConnectedCluster.id;
                currentClusterId = firstConnectedCluster.id;
                onClusterChange();
                loadExternalNetworks(); // 加载外部网络列表
            }
        } else {
            showAlert('加载集群失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error loading clusters:', error);
        showAlert('加载集群列表失败', 'danger');
    }
}

// 集群变化处理
function onClusterChange() {
    const select = document.getElementById('clusterSelect');
    const selectedValue = select.value;
    currentClusterId = selectedValue ? parseInt(selectedValue) : null;
    
    clearSelection();
    
    if (currentClusterId) {
        loadRouters();
        loadExternalNetworks();
    } else {
        clearRoutersTable();
    }
}

// 加载路由器列表
async function loadRouters() {
    if (!currentClusterId) return;
    
    showLoading(true);
    
    try {
        const params = new URLSearchParams({
            cluster_id: currentClusterId,
            page: currentPage,
            per_page: document.getElementById('perPageSelect').value
        });
        
        // 添加过滤条件
        const status = document.getElementById('statusFilter').value;
        const search = document.getElementById('searchInput').value.trim();
        
        if (status) params.append('status', status);
        if (search) params.append('search', search);
        
        const response = await fetch(`/api/routers?${params}`);
        const data = await response.json();
        
        if (data.success) {
            routersData = data.data;
            updateStatistics(data.statistics);
            updatePagination(data.pagination);
            renderRoutersTable(routersData);
        } else {
            showAlert('加载路由器失败: ' + data.error, 'danger');
            clearRoutersTable();
        }
    } catch (error) {
        console.error('Error loading routers:', error);
        showAlert('网络错误，请检查连接', 'danger');
        clearRoutersTable();
    } finally {
        showLoading(false);
    }
}

// 渲染路由器表格
function renderRoutersTable(routers) {
    const tbody = document.getElementById('routersTableBody');
    
    if (!routers || routers.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-4 text-muted">
                    <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                    没有找到路由器数据
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = routers.map(router => `
        <tr>
            <td>
                <input type="checkbox" class="form-check-input router-checkbox" 
                       value="${router.id}" onchange="updateSelection()">
            </td>
            <td>
                <div class="d-flex align-items-center">
                    <span class="router-status ${router.status}"></span>
                    <div>
                        <div class="fw-bold">${escapeHtml(router.name)}</div>
                        <small class="text-muted">${router.id}</small>
                    </div>
                </div>
            </td>
            <td>
                <span class="badge ${getStatusBadgeClass(router.status)}">${router.status}</span>
            </td>
            <td>
                ${router.external_gateway_info ? 
                    '<i class="fas fa-check-circle text-success" title="已配置外部网关"></i>' : 
                    '<i class="fas fa-times-circle text-muted" title="未配置外部网关"></i>'}
            </td>
            <td>
                ${router.admin_state_up ? 
                    '<span class="badge bg-success">启用</span>' : 
                    '<span class="badge bg-secondary">禁用</span>'}
            </td>
            <td>
                <span class="badge bg-info">${router.ports_count}</span>
            </td>
            <td>
                <span class="badge bg-secondary">${escapeHtml(router.cluster_name)}</span>
            </td>
            <td>
                <small>${formatDateTime(router.created_at)}</small>
            </td>
            <td>
                <div class="action-buttons">
                    <button type="button" class="btn btn-sm btn-outline-info" 
                            onclick="showRouterDetail('${router.id}')" title="查看详情">
                        <i class="fas fa-eye"></i>
                    </button>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle" 
                                data-bs-toggle="dropdown">
                            <i class="fas fa-cog"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="#" onclick="editRouter('${router.id}', '${escapeHtml(router.name)}')">
                                <i class="fas fa-edit me-2"></i>重命名
                            </a></li>
                            <li><a class="dropdown-item" href="#" onclick="toggleAdminState('${router.id}', ${router.admin_state_up})">
                                <i class="fas fa-${router.admin_state_up ? 'pause' : 'play'} me-2"></i>${router.admin_state_up ? '禁用' : '启用'}
                            </a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="#" onclick="deleteRouter('${router.id}', '${escapeHtml(router.name)}')">
                                <i class="fas fa-trash me-2"></i>删除
                            </a></li>
                        </ul>
                    </div>
                </div>
            </td>
        </tr>
    `).join('');
}

// 更新统计信息
function updateStatistics(statistics) {
    document.getElementById('totalRouters').textContent = statistics.total_routers;
    document.getElementById('activeRouters').textContent = statistics.status_counts?.ACTIVE || 0;
    document.getElementById('downRouters').textContent = statistics.status_counts?.DOWN || 0;
    document.getElementById('currentCluster').textContent = statistics.cluster_name;
}

// 更新分页信息
function updatePagination(pagination) {
    currentPage = pagination.page;
    totalPages = pagination.pages;
    
    // 更新分页信息文本
    const start = (pagination.page - 1) * pagination.per_page + 1;
    const end = Math.min(pagination.page * pagination.per_page, pagination.total);
    document.getElementById('paginationInfo').textContent = 
        `显示 ${start} - ${end} 条，共 ${pagination.total} 条记录`;
    
    // 生成分页按钮
    const paginationElement = document.getElementById('pagination');
    let paginationHTML = '';
    
    // 上一页按钮
    paginationHTML += `
        <li class="page-item ${!pagination.has_prev ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${pagination.page - 1})" 
               ${!pagination.has_prev ? 'tabindex="-1"' : ''}>上一页</a>
        </li>
    `;
    
    // 页码按钮
    let startPage = Math.max(1, pagination.page - 2);
    let endPage = Math.min(totalPages, pagination.page + 2);
    
    if (startPage > 1) {
        paginationHTML += '<li class="page-item"><a class="page-link" href="#" onclick="changePage(1)">1</a></li>';
        if (startPage > 2) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
    }
    
    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <li class="page-item ${i === pagination.page ? 'active' : ''}">
                <a class="page-link" href="#" onclick="changePage(${i})">${i}</a>
            </li>
        `;
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
        paginationHTML += `<li class="page-item"><a class="page-link" href="#" onclick="changePage(${totalPages})">${totalPages}</a></li>`;
    }
    
    // 下一页按钮
    paginationHTML += `
        <li class="page-item ${!pagination.has_next ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="changePage(${pagination.page + 1})"
               ${!pagination.has_next ? 'tabindex="-1"' : ''}>下一页</a>
        </li>
    `;
    
    paginationElement.innerHTML = paginationHTML;
}

// 页面切换
function changePage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadRouters();
}

// 应用过滤器
function applyFilters() {
    currentPage = 1;
    loadRouters();
}

// 刷新路由器列表
function refreshRouters() {
    currentPage = 1;
    clearSelection();
    loadRouters();
}

// 显示创建路由器模态框
function showCreateModal() {
    if (!currentClusterId) {
        showAlert('请先选择一个集群', 'warning');
        return;
    }
    
    // 重置表单
    document.getElementById('createRouterForm').reset();
    
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('createRouterModal'));
    modal.show();
}

// 加载外部网络列表
async function loadExternalNetworks() {
    if (!currentClusterId) return;
    
    try {
        const response = await fetch(`/api/routers/external-networks?cluster_id=${currentClusterId}`);
        const data = await response.json();
        
        if (data.success) {
            const select = document.getElementById('externalNetworkSelect');
            select.innerHTML = '<option value="">不设置外部网关</option>';
            
            data.data.forEach(network => {
                const option = document.createElement('option');
                option.value = network.id;
                option.textContent = `${network.name} (${network.status})`;
                if (network.status !== 'ACTIVE') {
                    option.disabled = true;
                }
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading external networks:', error);
    }
}

// 提交创建路由器
async function submitCreateRouter() {
    const formData = new FormData(document.getElementById('createRouterForm'));
    const data = {
        name: formData.get('name'),
        description: formData.get('description'),
        admin_state_up: formData.get('admin_state_up') === 'on',
        distributed: formData.get('distributed') === 'on',
        ha: formData.get('ha') === 'on'
    };
    
    const externalNetworkId = formData.get('external_network_id');
    if (externalNetworkId) {
        data.external_network_id = externalNetworkId;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/routers/create?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            bootstrap.Modal.getInstance(document.getElementById('createRouterModal')).hide();
            showAlert(result.message, 'success');
            loadRouters();
        } else {
            showAlert('创建失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error creating router:', error);
        showAlert('创建失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 显示路由器详情
async function showRouterDetail(routerId) {
    try {
        showLoading(true);
        const response = await fetch(`/api/routers/${routerId}?cluster_id=${currentClusterId}`);
        const data = await response.json();
        
        if (data.success) {
            const router = data.data;
            const content = document.getElementById('routerDetailContent');
            
            content.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <h6>基本信息</h6>
                        <table class="table table-sm">
                            <tr><td>名称:</td><td>${escapeHtml(router.name)}</td></tr>
                            <tr><td>ID:</td><td><code>${router.id}</code></td></tr>
                            <tr><td>状态:</td><td><span class="badge ${getStatusBadgeClass(router.status)}">${router.status}</span></td></tr>
                            <tr><td>管理状态:</td><td><span class="badge ${router.admin_state_up ? 'bg-success' : 'bg-secondary'}">${router.admin_state_up ? '启用' : '禁用'}</span></td></tr>
                            <tr><td>描述:</td><td>${escapeHtml(router.description) || '-'}</td></tr>
                            <tr><td>创建时间:</td><td>${formatDateTime(router.created_at)}</td></tr>
                        </table>
                    </div>
                    <div class="col-md-6">
                        <h6>网关信息</h6>
                        ${router.external_gateway_info ? `
                            <table class="table table-sm">
                                <tr><td>外部网络:</td><td>${router.external_gateway_info.network_id}</td></tr>
                                <tr><td>启用SNAT:</td><td>${router.external_gateway_info.enable_snat ? '是' : '否'}</td></tr>
                            </table>
                        ` : '<p class="text-muted">未配置外部网关</p>'}
                    </div>
                </div>
                
                <h6 class="mt-3">端口信息</h6>
                ${router.ports && router.ports.length > 0 ? `
                    <div class="table-responsive">
                        <table class="table table-sm table-striped">
                            <thead><tr><th>端口ID</th><th>网络</th><th>子网</th><th>IP地址</th><th>状态</th></tr></thead>
                            <tbody>
                                ${router.ports.map(port => `
                                    <tr>
                                        <td><code>${port.id}</code></td>
                                        <td>${port.network_id}</td>
                                        <td>${port.fixed_ips ? port.fixed_ips.map(ip => ip.subnet_id).join(', ') : '-'}</td>
                                        <td>${port.fixed_ips ? port.fixed_ips.map(ip => ip.ip_address).join(', ') : '-'}</td>
                                        <td><span class="badge ${getStatusBadgeClass(port.status)}">${port.status}</span></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '<p class="text-muted">没有端口信息</p>'}
            `;
            
            const modal = new bootstrap.Modal(document.getElementById('routerDetailModal'));
            modal.show();
        } else {
            showAlert('获取路由器详情失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error showing router detail:', error);
        showAlert('加载路由器详情失败', 'danger');
    } finally {
        showLoading(false);
    }
}

// 工具函数
function getStatusBadgeClass(status) {
    switch (status?.toUpperCase()) {
        case 'ACTIVE': return 'bg-success';
        case 'DOWN': return 'bg-danger';
        case 'BUILD': return 'bg-warning';
        case 'ERROR': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

function formatDateTime(dateString) {
    if (!dateString) return '-';
    try {
        return new Date(dateString).toLocaleString('zh-CN');
    } catch (e) {
        return dateString;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showAlert(message, type) {
    // 移除现有的警报
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());
    
    // 创建新的警报
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // 插入到主内容区域的顶部
    const mainContent = document.querySelector('main');
    mainContent.insertBefore(alertDiv, mainContent.firstChild);
    
    // 自动移除警报
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    overlay.style.display = show ? 'flex' : 'none';
}

function clearRoutersTable() {
    const tbody = document.getElementById('routersTableBody');
    tbody.innerHTML = `
        <tr>
            <td colspan="9" class="text-center py-4 text-muted">
                请选择集群查看路由器
            </td>
        </tr>
    `;
    updateStatistics({
        total_routers: 0,
        status_counts: {},
        cluster_name: '-'
    });
}

// 选择管理
function updateSelection() {
    selectedRouters.clear();
    const checkboxes = document.querySelectorAll('.router-checkbox:checked');
    checkboxes.forEach(cb => selectedRouters.add(cb.value));
    
    document.getElementById('selectedCount').textContent = `已选择: ${selectedRouters.size}`;
    
    const batchActions = document.getElementById('batchActions');
    batchActions.style.display = selectedRouters.size > 0 ? 'block' : 'none';
    
    const selectAllCheckbox = document.getElementById('selectAll');
    selectAllCheckbox.checked = selectedRouters.size === routersData.length;
    selectAllCheckbox.indeterminate = selectedRouters.size > 0 && selectedRouters.size < routersData.length;
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.router-checkbox');
    
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
    });
    
    updateSelection();
}

function clearSelection() {
    selectedRouters.clear();
    document.querySelectorAll('.router-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAll').checked = false;
    document.getElementById('selectAll').indeterminate = false;
    document.getElementById('selectedCount').textContent = '已选择: 0';
    document.getElementById('batchActions').style.display = 'none';
}

// 批量操作
async function batchAction(action) {
    if (selectedRouters.size === 0) {
        showAlert('请先选择要操作的路由器', 'warning');
        return;
    }
    
    const confirmMessage = `确定要${action === 'delete' ? '删除' : action === 'enable' ? '启用' : '禁用'}选中的 ${selectedRouters.size} 个路由器吗？`;
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/routers/batch-action?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                router_ids: Array.from(selectedRouters),
                action: action
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            clearSelection();
            loadRouters();
        } else {
            showAlert('批量操作失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error performing batch action:', error);
        showAlert('批量操作失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 导出功能
async function exportRouters() {
    if (!currentClusterId) {
        showAlert('请先选择一个集群', 'warning');
        return;
    }
    
    try {
        showLoading(true);
        
        const params = new URLSearchParams({
            cluster_id: currentClusterId
        });
        
        const response = await fetch(`/api/routers/export?${params}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                export_all: true,
                filters: {
                    status: document.getElementById('statusFilter').value,
                    search: document.getElementById('searchInput').value.trim()
                }
            })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `routers_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showAlert('导出成功', 'success');
        } else {
            const error = await response.json();
            showAlert('导出失败: ' + error.error, 'danger');
        }
    } catch (error) {
        console.error('Error exporting routers:', error);
        showAlert('导出失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}