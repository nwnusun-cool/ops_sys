/**
 * 安全组管理页面JavaScript
 */

let currentClusterId = null;
let securityGroupsData = [];
let currentPage = 1;
let totalPages = 1;
let selectedSecurityGroups = new Set();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('Security Groups page loaded');
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
    
    // 创建安全组表单提交
    document.getElementById('createSecurityGroupForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitCreateSecurityGroup();
    });
    
    // 添加规则表单提交
    document.getElementById('addRuleForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitAddRule();
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
        loadSecurityGroups();
    } else {
        clearSecurityGroupsTable();
    }
}

// 加载安全组列表
async function loadSecurityGroups() {
    if (!currentClusterId) return;
    
    showLoading(true);
    
    try {
        const params = new URLSearchParams({
            cluster_id: currentClusterId,
            page: currentPage,
            per_page: document.getElementById('perPageSelect').value
        });
        
        // 添加过滤条件
        const search = document.getElementById('searchInput').value.trim();
        
        if (search) params.append('search', search);
        
        const response = await fetch(`/api/security-groups?${params}`);
        const data = await response.json();
        
        if (data.success) {
            securityGroupsData = data.data;
            updateStatistics(data.statistics);
            updatePagination(data.pagination);
            renderSecurityGroupsTable(securityGroupsData);
        } else {
            showAlert('加载安全组失败: ' + data.error, 'danger');
            clearSecurityGroupsTable();
        }
    } catch (error) {
        console.error('Error loading security groups:', error);
        showAlert('网络错误，请检查连接', 'danger');
        clearSecurityGroupsTable();
    } finally {
        showLoading(false);
    }
}

// 渲染安全组表格
function renderSecurityGroupsTable(securityGroups) {
    const tbody = document.getElementById('securityGroupsTableBody');
    
    if (!securityGroups || securityGroups.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-4 text-muted">
                    <i class="fas fa-shield-alt fa-2x mb-2 d-block"></i>
                    没有找到安全组数据
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = securityGroups.map(sg => `
        <tr>
            <td>
                <input type="checkbox" class="form-check-input sg-checkbox" 
                       value="${sg.id}" onchange="updateSelection()"
                       ${sg.name === 'default' ? 'disabled title="默认安全组不能删除"' : ''}>
            </td>
            <td>
                <div>
                    <div class="fw-bold">${escapeHtml(sg.name)}</div>
                    <small class="text-muted">${sg.id}</small>
                </div>
            </td>
            <td>
                <small class="text-muted">${escapeHtml(sg.description) || '-'}</small>
            </td>
            <td>
                <span class="badge bg-primary">${sg.rules_count}</span>
            </td>
            <td>
                <div class="security-group-rules">
                    ${renderSecurityRules(sg.rules)}
                </div>
            </td>
            <td>
                <span class="badge bg-secondary">${escapeHtml(sg.cluster_name)}</span>
            </td>
            <td>
                <small>${formatDateTime(sg.created_at)}</small>
            </td>
            <td>
                <div class="action-buttons">
                    <button type="button" class="btn btn-sm btn-outline-info" 
                            onclick="showSecurityGroupDetail('${sg.id}')" title="查看详情">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-success" 
                            onclick="showAddRuleModal('${sg.id}')" title="添加规则">
                        <i class="fas fa-plus"></i>
                    </button>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle" 
                                data-bs-toggle="dropdown">
                            <i class="fas fa-cog"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="#" onclick="editSecurityGroup('${sg.id}', '${escapeHtml(sg.name)}')">
                                <i class="fas fa-edit me-2"></i>编辑描述
                            </a></li>
                            ${sg.name !== 'default' ? `
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item text-danger" href="#" onclick="deleteSecurityGroup('${sg.id}', '${escapeHtml(sg.name)}')">
                                    <i class="fas fa-trash me-2"></i>删除
                                </a></li>
                            ` : ''}
                        </ul>
                    </div>
                </div>
            </td>
        </tr>
    `).join('');
}

// 渲染安全规则
function renderSecurityRules(rules) {
    if (!rules || rules.length === 0) {
        return '<small class="text-muted">无规则</small>';
    }
    
    return rules.slice(0, 3).map(rule => `
        <div class="rule-item">
            <span class="rule-direction ${rule.direction}">${rule.direction.toUpperCase()}</span>
            <span class="rule-protocol">${rule.protocol || 'ANY'}</span>
            <span class="rule-port">${rule.port_range || 'ANY'}</span>
            <span class="rule-remote">${rule.remote || 'ANY'}</span>
        </div>
    `).join('') + (rules.length > 3 ? `<small class="text-muted">还有 ${rules.length - 3} 条规则...</small>` : '');
}

// 更新统计信息
function updateStatistics(statistics) {
    document.getElementById('totalSecurityGroups').textContent = statistics.total_security_groups;
    document.getElementById('filteredSecurityGroups').textContent = statistics.filtered_security_groups;
    
    // 计算总规则数
    const totalRules = securityGroupsData.reduce((sum, sg) => sum + (sg.rules_count || 0), 0);
    document.getElementById('totalRules').textContent = totalRules;
    
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
    loadSecurityGroups();
}

// 应用过滤器
function applyFilters() {
    currentPage = 1;
    loadSecurityGroups();
}

// 清除过滤器
function clearFilters() {
    document.getElementById('searchInput').value = '';
    applyFilters();
}

// 刷新安全组列表
function refreshSecurityGroups() {
    currentPage = 1;
    clearSelection();
    loadSecurityGroups();
}

// 显示创建安全组模态框
function showCreateModal() {
    if (!currentClusterId) {
        showAlert('请先选择一个集群', 'warning');
        return;
    }
    
    // 重置表单
    document.getElementById('createSecurityGroupForm').reset();
    document.getElementById('initialRules').innerHTML = `
        <div class="mb-3">
            <button type="button" class="btn btn-sm btn-outline-primary" onclick="addInitialRule()">
                <i class="fas fa-plus me-1"></i>添加规则
            </button>
        </div>
    `;
    
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('createSecurityGroupModal'));
    modal.show();
}

// 显示添加规则模态框
function showAddRuleModal(securityGroupId) {
    document.getElementById('ruleSecurityGroupId').value = securityGroupId;
    document.getElementById('addRuleForm').reset();
    toggleRemoteFields(); // 初始化远程字段显示
    
    const modal = new bootstrap.Modal(document.getElementById('addRuleModal'));
    modal.show();
}

// 切换端口字段显示
function togglePortFields(selectElement) {
    const portFields = document.getElementById('portFields');
    const protocol = selectElement.value;
    
    if (protocol === 'tcp' || protocol === 'udp') {
        portFields.style.display = 'block';
    } else {
        portFields.style.display = 'none';
    }
}

// 切换远程字段显示
function toggleRemoteFields() {
    const remoteType = document.querySelector('input[name="remote_type"]:checked').value;
    const remoteCidr = document.getElementById('remoteCidr');
    const remoteGroup = document.getElementById('remoteGroup');
    
    if (remoteType === 'cidr') {
        remoteCidr.style.display = 'block';
        remoteGroup.style.display = 'none';
    } else {
        remoteCidr.style.display = 'none';
        remoteGroup.style.display = 'block';
        loadSecurityGroupsForSelect();
    }
}

// 加载安全组列表用于选择
async function loadSecurityGroupsForSelect() {
    try {
        const response = await fetch(`/api/security-groups?cluster_id=${currentClusterId}&per_page=100`);
        const data = await response.json();
        
        if (data.success) {
            const select = document.getElementById('remoteGroup');
            select.innerHTML = '<option value="">选择安全组</option>';
            
            data.data.forEach(sg => {
                const option = document.createElement('option');
                option.value = sg.id;
                option.textContent = sg.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading security groups for select:', error);
    }
}

// 提交创建安全组
async function submitCreateSecurityGroup() {
    const formData = new FormData(document.getElementById('createSecurityGroupForm'));
    const data = {
        name: formData.get('name'),
        description: formData.get('description')
    };
    
    // TODO: 收集初始规则（如果有的话）
    
    try {
        showLoading(true);
        const response = await fetch(`/api/security-groups/create?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            bootstrap.Modal.getInstance(document.getElementById('createSecurityGroupModal')).hide();
            showAlert(result.message, 'success');
            loadSecurityGroups();
        } else {
            showAlert('创建失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error creating security group:', error);
        showAlert('创建失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 提交添加规则
async function submitAddRule() {
    const formData = new FormData(document.getElementById('addRuleForm'));
    const securityGroupId = formData.get('security_group_id');
    
    const ruleData = {
        direction: formData.get('direction'),
        ethertype: formData.get('ethertype'),
        protocol: formData.get('protocol') === 'any' ? null : formData.get('protocol'),
        description: formData.get('description')
    };
    
    // 端口范围
    if (formData.get('port_range_min')) {
        ruleData.port_range_min = parseInt(formData.get('port_range_min'));
    }
    if (formData.get('port_range_max')) {
        ruleData.port_range_max = parseInt(formData.get('port_range_max'));
    }
    
    // 远程配置
    const remoteType = formData.get('remote_type');
    if (remoteType === 'cidr') {
        const cidr = formData.get('remote_ip_prefix');
        if (cidr) {
            ruleData.remote_ip_prefix = cidr;
        }
    } else {
        const groupId = formData.get('remote_group_id');
        if (groupId) {
            ruleData.remote_group_id = groupId;
        }
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/security-groups/${securityGroupId}/action?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'add_rule',
                rule: ruleData
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            bootstrap.Modal.getInstance(document.getElementById('addRuleModal')).hide();
            showAlert(result.message, 'success');
            loadSecurityGroups();
        } else {
            showAlert('添加规则失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error adding rule:', error);
        showAlert('添加规则失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 显示安全组详情
async function showSecurityGroupDetail(securityGroupId) {
    try {
        showLoading(true);
        const response = await fetch(`/api/security-groups/${securityGroupId}?cluster_id=${currentClusterId}`);
        const data = await response.json();
        
        if (data.success) {
            const sg = data.data;
            const content = document.getElementById('securityGroupDetailContent');
            
            content.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <h6>基本信息</h6>
                        <table class="table table-sm">
                            <tr><td>名称:</td><td>${escapeHtml(sg.name)}</td></tr>
                            <tr><td>ID:</td><td><code>${sg.id}</code></td></tr>
                            <tr><td>描述:</td><td>${escapeHtml(sg.description) || '-'}</td></tr>
                            <tr><td>规则数量:</td><td><span class="badge bg-primary">${sg.rules.length}</span></td></tr>
                            <tr><td>创建时间:</td><td>${formatDateTime(sg.created_at)}</td></tr>
                            <tr><td>集群:</td><td>${escapeHtml(sg.cluster_name)}</td></tr>
                        </table>
                    </div>
                    <div class="col-md-6">
                        <div class="d-flex justify-content-between align-items-center">
                            <h6>安全规则</h6>
                            <button type="button" class="btn btn-sm btn-primary" onclick="showAddRuleModal('${sg.id}')">
                                <i class="fas fa-plus me-1"></i>添加规则
                            </button>
                        </div>
                        <div style="max-height: 300px; overflow-y: auto;">
                            ${renderDetailedRules(sg.rules, sg.id)}
                        </div>
                    </div>
                </div>
            `;
            
            const modal = new bootstrap.Modal(document.getElementById('securityGroupDetailModal'));
            modal.show();
        } else {
            showAlert('获取安全组详情失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error showing security group detail:', error);
        showAlert('加载安全组详情失败', 'danger');
    } finally {
        showLoading(false);
    }
}

// 渲染详细规则
function renderDetailedRules(rules, securityGroupId) {
    if (!rules || rules.length === 0) {
        return '<p class="text-muted">没有安全规则</p>';
    }
    
    return `
        <div class="table-responsive">
            <table class="table table-sm table-striped">
                <thead>
                    <tr>
                        <th>方向</th>
                        <th>协议</th>
                        <th>端口范围</th>
                        <th>远程</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${rules.map(rule => `
                        <tr>
                            <td><span class="rule-direction ${rule.direction}">${rule.direction.toUpperCase()}</span></td>
                            <td><span class="rule-protocol">${rule.protocol || 'ANY'}</span></td>
                            <td><span class="rule-port">${rule.port_range || 'ANY'}</span></td>
                            <td><span class="rule-remote">${rule.remote || 'ANY'}</span></td>
                            <td>
                                <button type="button" class="btn btn-sm btn-outline-danger" 
                                        onclick="deleteRule('${securityGroupId}', '${rule.id}')" title="删除规则">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

// 删除规则
async function deleteRule(securityGroupId, ruleId) {
    if (!confirm('确定要删除这条安全规则吗？')) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/security-groups/${securityGroupId}/action?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'delete_rule',
                rule_id: ruleId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            loadSecurityGroups();
            // 如果详情模态框是打开的，重新加载详情
            const detailModal = document.getElementById('securityGroupDetailModal');
            if (detailModal.classList.contains('show')) {
                showSecurityGroupDetail(securityGroupId);
            }
        } else {
            showAlert('删除规则失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error deleting rule:', error);
        showAlert('删除规则失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 工具函数
function formatDateTime(dateString) {
    if (!dateString) return '-';
    try {
        return new Date(dateString).toLocaleString('zh-CN');
    } catch (e) {
        return dateString;
    }
}

function escapeHtml(text) {
    if (!text) return '';
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

function clearSecurityGroupsTable() {
    const tbody = document.getElementById('securityGroupsTableBody');
    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="text-center py-4 text-muted">
                请选择集群查看安全组
            </td>
        </tr>
    `;
    updateStatistics({
        total_security_groups: 0,
        filtered_security_groups: 0,
        cluster_name: '-'
    });
}

// 选择管理
function updateSelection() {
    selectedSecurityGroups.clear();
    const checkboxes = document.querySelectorAll('.sg-checkbox:checked:not(:disabled)');
    checkboxes.forEach(cb => selectedSecurityGroups.add(cb.value));
    
    document.getElementById('selectedCount').textContent = `已选择: ${selectedSecurityGroups.size}`;
    
    const batchActions = document.getElementById('batchActions');
    batchActions.style.display = selectedSecurityGroups.size > 0 ? 'block' : 'none';
    
    const selectAllCheckbox = document.getElementById('selectAll');
    const enabledCheckboxes = document.querySelectorAll('.sg-checkbox:not(:disabled)');
    selectAllCheckbox.checked = selectedSecurityGroups.size === enabledCheckboxes.length;
    selectAllCheckbox.indeterminate = selectedSecurityGroups.size > 0 && selectedSecurityGroups.size < enabledCheckboxes.length;
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.sg-checkbox:not(:disabled)');
    
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
    });
    
    updateSelection();
}

function clearSelection() {
    selectedSecurityGroups.clear();
    document.querySelectorAll('.sg-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAll').checked = false;
    document.getElementById('selectAll').indeterminate = false;
    document.getElementById('selectedCount').textContent = '已选择: 0';
    document.getElementById('batchActions').style.display = 'none';
}

// 批量操作
async function batchAction(action) {
    if (selectedSecurityGroups.size === 0) {
        showAlert('请先选择要操作的安全组', 'warning');
        return;
    }
    
    const confirmMessage = `确定要删除选中的 ${selectedSecurityGroups.size} 个安全组吗？`;
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/security-groups/batch-action?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                security_group_ids: Array.from(selectedSecurityGroups),
                action: action
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            clearSelection();
            loadSecurityGroups();
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
async function exportSecurityGroups() {
    if (!currentClusterId) {
        showAlert('请先选择一个集群', 'warning');
        return;
    }
    
    try {
        showLoading(true);
        
        const params = new URLSearchParams({
            cluster_id: currentClusterId
        });
        
        const response = await fetch(`/api/security-groups/export?${params}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                export_all: true,
                filters: {
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
            a.download = `security_groups_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showAlert('导出成功', 'success');
        } else {
            const error = await response.json();
            showAlert('导出失败: ' + error.error, 'danger');
        }
    } catch (error) {
        console.error('Error exporting security groups:', error);
        showAlert('导出失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}