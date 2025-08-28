/**
 * 用户管理页面JavaScript
 */

let usersData = [];
let currentPage = 1;
let totalPages = 1;
let selectedUsers = new Set();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('Users page loaded');
    loadUsers();
    setupEventListeners();
});

// 设置事件监听器
function setupEventListeners() {
    // 过滤表单提交
    document.getElementById('filterForm').addEventListener('submit', function(e) {
        e.preventDefault();
        applyFilters();
    });
    
    // 创建用户表单提交
    document.getElementById('createUserForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitCreateUser();
    });
    
    // 编辑用户表单提交
    document.getElementById('editUserForm').addEventListener('submit', function(e) {
        e.preventDefault();
        submitEditUser();
    });
    
    // 搜索输入框回车
    document.getElementById('searchInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            applyFilters();
        }
    });
}

// 加载用户列表
async function loadUsers() {
    showLoading(true);
    
    try {
        const params = new URLSearchParams({
            page: currentPage,
            per_page: document.getElementById('perPageSelect').value
        });
        
        // 添加过滤条件
        const role = document.getElementById('roleFilter').value;
        const status = document.getElementById('statusFilter').value;
        const search = document.getElementById('searchInput').value.trim();
        
        if (role) params.append('role', role);
        if (status) params.append('is_active', status);
        if (search) params.append('search', search);
        
        const response = await fetch(`/api/users?${params}`);
        const data = await response.json();
        
        if (data.success) {
            usersData = data.data;
            updateStatistics(data.statistics);
            updatePagination(data.pagination);
            renderUsersTable(usersData);
        } else {
            showAlert('加载用户失败: ' + data.error, 'danger');
            clearUsersTable();
        }
    } catch (error) {
        console.error('Error loading users:', error);
        showAlert('网络错误，请检查连接', 'danger');
        clearUsersTable();
    } finally {
        showLoading(false);
    }
}

// 渲染用户表格
function renderUsersTable(users) {
    const tbody = document.getElementById('usersTableBody');
    
    if (!users || users.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-4 text-muted">
                    <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                    没有找到用户数据
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = users.map(user => `
        <tr class="${getStatusRowClass(user)}">
            <td>
                <input type="checkbox" class="form-check-input user-checkbox" 
                       value="${user.id}" onchange="updateSelection()" 
                       ${user.id === getCurrentUserId() ? 'disabled title="不能选择自己"' : ''}>
            </td>
            <td>
                <div class="d-flex align-items-center">
                    <div class="user-avatar me-2">
                        ${getUserInitials(user.username)}
                    </div>
                    <div>
                        <div class="fw-bold">${escapeHtml(user.username)}</div>
                        <small class="text-muted">${escapeHtml(user.email)}</small>
                    </div>
                </div>
            </td>
            <td>
                <span class="role-badge ${getRoleBadgeClass(user.role)}">${getRoleDisplayName(user.role)}</span>
            </td>
            <td>
                <div class="user-status">
                    <span class="status-dot ${user.is_active ? 'success' : 'neutral'}"></span>
                    <span class="badge ${user.is_active ? 'bg-success' : 'bg-neutral'}">${user.is_active ? '启用' : '禁用'}</span>
                </div>
            </td>
            <td>
                <small>${user.last_login ? formatDateTime(user.last_login) : '从未登录'}</small>
            </td>
            <td>
                <span class="badge bg-info">${user.login_count}</span>
            </td>
            <td>
                <small>${formatDateTime(user.created_at)}</small>
            </td>
            <td>
                <div class="action-buttons">
                    <button type="button" class="btn btn-sm btn-outline-info" 
                            onclick="showUserDetail(${user.id})" title="查看详情">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-primary" 
                            onclick="editUser(${user.id})" title="编辑">
                        <i class="fas fa-edit"></i>
                    </button>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle" 
                                data-bs-toggle="dropdown">
                            <i class="fas fa-cog"></i>
                        </button>
                        <ul class="dropdown-menu">
                            ${user.is_active ? 
                                `<li><a class="dropdown-item" href="#" onclick="toggleUserStatus(${user.id}, false)">
                                    <i class="fas fa-pause me-2"></i>禁用
                                </a></li>` :
                                `<li><a class="dropdown-item" href="#" onclick="toggleUserStatus(${user.id}, true)">
                                    <i class="fas fa-play me-2"></i>启用
                                </a></li>`
                            }
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="#" onclick="deleteUser(${user.id}, '${escapeHtml(user.username)}')" 
                                   ${user.id === getCurrentUserId() ? 'style="display:none"' : ''}>
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
    document.getElementById('totalUsers').textContent = statistics.total_users;
    document.getElementById('activeUsers').textContent = statistics.active_users;
    document.getElementById('inactiveUsers').textContent = statistics.inactive_users;
    document.getElementById('adminUsers').textContent = 
        (statistics.role_counts?.admin || 0) + (statistics.role_counts?.super_admin || 0);
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
    loadUsers();
}

// 应用过滤器
function applyFilters() {
    currentPage = 1;
    loadUsers();
}

// 清除过滤器
function clearFilters() {
    document.getElementById('searchInput').value = '';
    document.getElementById('roleFilter').value = '';
    document.getElementById('statusFilter').value = '';
    applyFilters();
}

// 刷新用户列表
function refreshUsers() {
    currentPage = 1;
    clearSelection();
    loadUsers();
}

// 显示创建用户模态框
function showCreateModal() {
    // 重置表单
    document.getElementById('createUserForm').reset();
    document.getElementById('createIsActive').checked = true;
    
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('createUserModal'));
    modal.show();
}

// 提交创建用户
async function submitCreateUser() {
    const formData = new FormData(document.getElementById('createUserForm'));
    const data = {
        username: formData.get('username'),
        email: formData.get('email'),
        password: formData.get('password'),
        role: formData.get('role'),
        is_active: formData.get('is_active') === 'on'
    };
    
    try {
        showLoading(true);
        const response = await fetch('/api/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            bootstrap.Modal.getInstance(document.getElementById('createUserModal')).hide();
            showAlert(result.message, 'success');
            loadUsers();
        } else {
            showAlert('创建失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error creating user:', error);
        showAlert('创建失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 编辑用户
function editUser(userId) {
    const user = usersData.find(u => u.id === userId);
    if (!user) return;
    
    // 填充表单
    document.getElementById('editUserId').value = user.id;
    document.getElementById('editUsername').value = user.username;
    document.getElementById('editEmail').value = user.email;
    document.getElementById('editRole').value = user.role;
    document.getElementById('editIsActive').checked = user.is_active;
    document.getElementById('editPassword').value = '';
    
    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('editUserModal'));
    modal.show();
}

// 提交编辑用户
async function submitEditUser() {
    const formData = new FormData(document.getElementById('editUserForm'));
    const userId = formData.get('user_id');
    const data = {
        username: formData.get('username'),
        email: formData.get('email'),
        role: formData.get('role'),
        is_active: formData.get('is_active') === 'on'
    };
    
    // 只有在输入了密码时才包含密码字段
    const password = formData.get('password');
    if (password && password.trim()) {
        data.password = password;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            bootstrap.Modal.getInstance(document.getElementById('editUserModal')).hide();
            showAlert(result.message, 'success');
            loadUsers();
        } else {
            showAlert('更新失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error updating user:', error);
        showAlert('更新失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 显示用户详情
async function showUserDetail(userId) {
    try {
        showLoading(true);
        const response = await fetch(`/api/users/${userId}`);
        const data = await response.json();
        
        if (data.success) {
            const user = data.data;
            const content = document.getElementById('userDetailContent');
            
            content.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <h6>基本信息</h6>
                        <table class="table table-sm">
                            <tr><td>用户名:</td><td><strong>${escapeHtml(user.username)}</strong></td></tr>
                            <tr><td>邮箱:</td><td>${escapeHtml(user.email)}</td></tr>
                            <tr><td>角色:</td><td><span class="role-badge ${getRoleBadgeClass(user.role)}">${getRoleDisplayName(user.role)}</span></td></tr>
                            <tr><td>状态:</td><td><span class="badge ${user.is_active ? 'bg-success' : 'bg-neutral'}">${user.is_active ? '启用' : '禁用'}</span></td></tr>
                            <tr><td>创建时间:</td><td>${formatDateTime(user.created_at)}</td></tr>
                            <tr><td>更新时间:</td><td>${formatDateTime(user.updated_at)}</td></tr>
                        </table>
                    </div>
                    <div class="col-md-6">
                        <h6>登录统计</h6>
                        <table class="table table-sm">
                            <tr><td>登录次数:</td><td><span class="badge bg-info">${user.login_count}</span></td></tr>
                            <tr><td>最后登录:</td><td>${user.last_login ? formatDateTime(user.last_login) : '从未登录'}</td></tr>
                            <tr><td>操作记录:</td><td><span class="badge bg-secondary">${user.operation_logs_count}</span></td></tr>
                        </table>
                    </div>
                </div>
                
                <h6 class="mt-3">最近操作记录</h6>
                ${user.recent_operations && user.recent_operations.length > 0 ? `
                    <div class="table-responsive">
                        <table class="table table-sm table-striped">
                            <thead><tr><th>时间</th><th>操作类型</th><th>操作对象</th><th>集群</th><th>结果</th><th>详情</th></tr></thead>
                            <tbody>
                                ${user.recent_operations.map(op => `
                                    <tr>
                                        <td><small>${formatDateTime(op.created_at)}</small></td>
                                        <td><code>${op.operation_type}</code></td>
                                        <td><small>${escapeHtml(op.operation_object)}</small></td>
                                        <td><small>${op.cluster_name || '-'}</small></td>
                                        <td><span class="badge ${op.result === 'success' ? 'bg-success' : 'bg-danger'}">${op.result}</span></td>
                                        <td><small>${escapeHtml(op.details)}</small></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '<p class="text-muted">没有操作记录</p>'}
            `;
            
            const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
            modal.show();
        } else {
            showAlert('获取用户详情失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Error showing user detail:', error);
        showAlert('加载用户详情失败', 'danger');
    } finally {
        showLoading(false);
    }
}

// 切换用户状态
async function toggleUserStatus(userId, newStatus) {
    const user = usersData.find(u => u.id === userId);
    if (!user) return;
    
    const action = newStatus ? '启用' : '禁用';
    if (!confirm(`确定要${action}用户 "${user.username}" 吗？`)) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                is_active: newStatus
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            loadUsers();
        } else {
            showAlert(`${action}失败: ` + result.error, 'danger');
        }
    } catch (error) {
        console.error(`Error toggling user status:`, error);
        showAlert(`${action}失败，请检查网络连接`, 'danger');
    } finally {
        showLoading(false);
    }
}

// 删除用户
async function deleteUser(userId, username) {
    if (!confirm(`确定要删除用户 "${username}" 吗？此操作不可逆！`)) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch(`/api/users/${userId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            loadUsers();
        } else {
            showAlert('删除失败: ' + result.error, 'danger');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showAlert('删除失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 选择管理
function updateSelection() {
    selectedUsers.clear();
    const checkboxes = document.querySelectorAll('.user-checkbox:checked:not(:disabled)');
    checkboxes.forEach(cb => selectedUsers.add(parseInt(cb.value)));
    
    document.getElementById('selectedCount').textContent = `已选择: ${selectedUsers.size}`;
    
    const batchPanel = document.getElementById('batchActionsPanel');
    if (selectedUsers.size > 0) {
        batchPanel.classList.add('show');
    } else {
        batchPanel.classList.remove('show');
    }
    
    const selectAllCheckbox = document.getElementById('selectAll');
    const enabledCheckboxes = document.querySelectorAll('.user-checkbox:not(:disabled)');
    selectAllCheckbox.checked = selectedUsers.size === enabledCheckboxes.length;
    selectAllCheckbox.indeterminate = selectedUsers.size > 0 && selectedUsers.size < enabledCheckboxes.length;
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.user-checkbox:not(:disabled)');
    
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
    });
    
    updateSelection();
}

function clearSelection() {
    selectedUsers.clear();
    document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAll').checked = false;
    document.getElementById('selectAll').indeterminate = false;
    document.getElementById('selectedCount').textContent = '已选择: 0';
    document.getElementById('batchActionsPanel').classList.remove('show');
}

// 批量操作
async function batchAction(action) {
    if (selectedUsers.size === 0) {
        showAlert('请先选择要操作的用户', 'warning');
        return;
    }
    
    const actionText = {
        'delete': '删除',
        'enable': '启用',
        'disable': '禁用'
    };
    
    const confirmMessage = `确定要${actionText[action]}选中的 ${selectedUsers.size} 个用户吗？`;
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    try {
        showLoading(true);
        const response = await fetch('/api/users/batch-action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_ids: Array.from(selectedUsers),
                action: action
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(result.message, 'success');
            clearSelection();
            loadUsers();
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
async function exportUsers() {
    try {
        showLoading(true);
        
        const response = await fetch('/api/users/export', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                export_all: true,
                filters: {
                    role: document.getElementById('roleFilter').value,
                    is_active: document.getElementById('statusFilter').value,
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
            a.download = `users_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showAlert('导出成功', 'success');
        } else {
            const error = await response.json();
            showAlert('导出失败: ' + error.error, 'danger');
        }
    } catch (error) {
        console.error('Error exporting users:', error);
        showAlert('导出失败，请检查网络连接', 'danger');
    } finally {
        showLoading(false);
    }
}

// 工具函数
function getCurrentUserId() {
    // 从页面获取当前用户ID（需要在模板中设置）
    return window.currentUserId || 0;
}

function getUserInitials(username) {
    if (!username) return '?';
    const words = username.split(/[\s_-]+/);
    if (words.length >= 2) {
        return (words[0][0] + words[1][0]).toUpperCase();
    }
    return username.substring(0, 2).toUpperCase();
}

function getStatusRowClass(user) {
    return user.is_active ? 'status-active' : 'status-inactive';
}

function getRoleBadgeClass(role) {
    const classMap = {
        'super_admin': 'role-super-admin',
        'admin': 'role-admin',
        'operator': 'role-operator',
        'viewer': 'role-viewer'
    };
    return classMap[role] || 'role-viewer';
}

function getRoleDisplayName(role) {
    const nameMap = {
        'super_admin': '超级管理员',
        'admin': '管理员',
        'operator': '操作员',
        'viewer': '查看者'
    };
    return nameMap[role] || role;
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
    const indicator = document.getElementById('loadingIndicator');
    indicator.style.display = show ? 'block' : 'none';
}

function clearUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="text-center py-4 text-muted">
                请检查网络连接或联系管理员
            </td>
        </tr>
    `;
    updateStatistics({
        total_users: 0,
        active_users: 0,
        inactive_users: 0,
        role_counts: {}
    });
}