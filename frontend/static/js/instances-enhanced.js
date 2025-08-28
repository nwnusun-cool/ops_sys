// 增强功能的JavaScript函数

// 全局变量声明
let current_user_is_admin = true; // 这个值应该从后端传递

// 切换视图模式
function toggleView() {
    const cardView = document.getElementById('cardView');
    const tableView = document.getElementById('tableView');
    const viewToggle = document.getElementById('viewToggle');
    const batchSelectHeader = document.getElementById('batchSelectHeader');
    
    if (currentView === 'card') {
        // 切换到表格视图
        cardView.style.display = 'none';
        tableView.style.display = 'block';
        viewToggle.innerHTML = '<i class="fas fa-table me-1"></i>表格视图';
        currentView = 'table';
        
        // 在表格视图中显示批量选择
        if (isBatchMode) {
            batchSelectHeader.style.display = 'table-cell';
        }
        
        // 重新渲染数据为表格格式
        loadInstances(currentPage);
    } else {
        // 切换到卡片视图
        cardView.style.display = 'block';
        tableView.style.display = 'none';
        viewToggle.innerHTML = '<i class="fas fa-th me-1"></i>卡片视图';
        currentView = 'card';
        
        // 重新渲染数据为卡片格式
        loadInstances(currentPage);
    }
}

// 渲染表格视图
function renderInstanceTable(instances) {
    const tbody = document.getElementById('instancesTableBody');
    
    if (instances.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${isBatchMode ? '8' : '7'}" class="text-center text-muted">没有找到实例</td></tr>`;
        return;
    }
    
    tbody.innerHTML = instances.map(instance => `
        <tr data-instance-id="${instance.id}" ${selectedInstances.has(instance.id) ? 'class="table-active"' : ''}>
            ${isBatchMode ? `
            <td>
                <input type="checkbox" class="instance-checkbox" value="${instance.id}" 
                       ${selectedInstances.has(instance.id) ? 'checked' : ''} 
                       onchange="toggleInstanceSelection('${instance.id}')">
            </td>
            ` : ''}
            <td>
                <strong>${instance.name}</strong>
                ${instance.metadata && instance.metadata.destroy_at ? 
                    `<br><small class="text-danger"><i class="fas fa-clock"></i> 销毁: ${formatTime(instance.metadata.destroy_at)}</small>` : ''
                }
            </td>
            <td>
                <span class="badge ${getStatusClass(instance.status)}">
                    ${getStatusText(instance.status)}
                </span>
            </td>
            <td>${instance.flavor.name}</td>
            <td>${instance.image.name}</td>
            <td>${getInstanceIPsText(instance.addresses)}</td>
            <td>${formatTime(instance.created)}</td>
            <td>
                <div class="dropdown">
                    <button class="btn btn-sm btn-outline-secondary" data-bs-toggle="dropdown">
                        <i class="fas fa-ellipsis-v"></i>
                    </button>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item" href="#" onclick="viewInstanceDetail('${instance.id}')">
                            <i class="fas fa-eye me-2"></i>查看详情
                        </a></li>
                        <li><a class="dropdown-item" href="#" onclick="openConsole('${instance.id}')">
                            <i class="fas fa-terminal me-2"></i>控制台
                        </a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="#" onclick="renameInstance('${instance.id}', '${instance.name}')">
                            <i class="fas fa-edit me-2"></i>重命名
                        </a></li>
                        <li><a class="dropdown-item" href="#" onclick="setDestroyTimer('${instance.id}', '${instance.name}')">
                            <i class="fas fa-clock me-2 text-warning"></i>设置销毁时间
                        </a></li>
                        <li><hr class="dropdown-divider"></li>
                        ${getActionMenuItems(instance)}
                    </ul>
                </div>
            </td>
        </tr>
    `).join('');
}

// 获取IP地址的文本格式
function getInstanceIPsText(addresses) {
    if (!addresses || Object.keys(addresses).length === 0) {
        return '无';
    }
    
    let ips = [];
    for (const [network, addrs] of Object.entries(addresses)) {
        addrs.forEach(addr => {
            ips.push(`${network}:${addr.addr}`);
        });
    }
    return ips.join('<br>');
}

// 切换批量模式
function toggleBatchMode() {
    isBatchMode = !isBatchMode;
    
    const batchToolbar = document.getElementById('batchToolbar');
    const batchOperationBtn = document.getElementById('batchOperationBtn');
    const batchSelectHeader = document.getElementById('batchSelectHeader');
    
    if (isBatchMode) {
        batchToolbar.style.display = 'block';
        batchOperationBtn.innerHTML = '<i class="fas fa-times me-1"></i>退出批量';
        batchOperationBtn.className = 'btn btn-outline-danger';
        
        if (currentView === 'table') {
            batchSelectHeader.style.display = 'table-cell';
        }
    } else {
        batchToolbar.style.display = 'none';
        batchOperationBtn.innerHTML = '<i class="fas fa-tasks me-1"></i>批量操作';
        batchOperationBtn.className = 'btn btn-outline-primary';
        
        if (currentView === 'table') {
            batchSelectHeader.style.display = 'none';
        }
        
        // 清除选择
        clearSelection();
    }
    
    // 重新渲染列表
    loadInstances(currentPage);
}

// 切换实例选择状态
function toggleInstanceSelection(instanceId) {
    if (selectedInstances.has(instanceId)) {
        selectedInstances.delete(instanceId);
    } else {
        selectedInstances.add(instanceId);
    }
    
    updateSelectedCount();
    updateSelectAllCheckbox();
    
    // 更新视觉效果
    const element = document.querySelector(`[data-instance-id="${instanceId}"]`);
    if (element) {
        if (selectedInstances.has(instanceId)) {
            if (currentView === 'card') {
                element.classList.add('border-primary');
            } else {
                element.classList.add('table-active');
            }
        } else {
            if (currentView === 'card') {
                element.classList.remove('border-primary');
            } else {
                element.classList.remove('table-active');
            }
        }
    }
}

// 全选/取消全选
function selectAllInstances() {
    const checkboxes = document.querySelectorAll('.instance-checkbox');
    checkboxes.forEach(checkbox => {
        selectedInstances.add(checkbox.value);
        checkbox.checked = true;
    });
    
    updateSelectedCount();
    updateSelectAllCheckbox();
    
    // 更新卡片样式
    if (currentView === 'card') {
        document.querySelectorAll('.instance-card').forEach(card => {
            card.classList.add('border-primary');
        });
    } else {
        document.querySelectorAll('#instancesTableBody tr').forEach(row => {
            row.classList.add('table-active');
        });
    }
}

// 清除选择
function clearSelection() {
    selectedInstances.clear();
    
    // 取消所有复选框选中状态
    document.querySelectorAll('.instance-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    
    // 移除卡片高亮
    document.querySelectorAll('.instance-card').forEach(card => {
        card.classList.remove('border-primary');
    });
    
    // 移除表格行高亮
    document.querySelectorAll('#instancesTableBody tr').forEach(row => {
        row.classList.remove('table-active');
    });
    
    updateSelectedCount();
    updateSelectAllCheckbox();
}

// 更新选中数量显示
function updateSelectedCount() {
    document.getElementById('selectedCount').textContent = `已选择 ${selectedInstances.size} 个实例`;
}

// 更新全选复选框状态
function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (!selectAllCheckbox) return;
    
    const checkboxes = document.querySelectorAll('.instance-checkbox');
    
    if (checkboxes.length === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
        return;
    }
    
    const checkedCount = selectedInstances.size;
    
    if (checkedCount === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
    } else if (checkedCount === checkboxes.length) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = true;
    } else {
        selectAllCheckbox.indeterminate = true;
    }
}

// 全选复选框切换
function toggleSelectAll() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    
    if (selectAllCheckbox.checked) {
        selectAllInstances();
    } else {
        clearSelection();
    }
}

// 批量操作
async function batchAction(action) {
    if (selectedInstances.size === 0) {
        showAlert('请先选择要操作的实例', 'warning');
        return;
    }
    
    const instanceIds = Array.from(selectedInstances);
    const actionNames = {
        'start': '启动',
        'stop': '停止',
        'restart': '重启',
        'delete': '删除'
    };
    
    if (!confirm(`确定要${actionNames[action]} ${instanceIds.length} 个实例吗？`)) {
        return;
    }
    
    try {
        showLoading(true);
        
        const response = await fetch(`/api/instances/batch-action?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                instance_ids: instanceIds,
                action: action,
                restart_type: action === 'restart' ? 'soft' : undefined
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showBatchResults(data);
            clearSelection();
            
            // 延迟刷新列表
            setTimeout(() => {
                loadInstances(currentPage);
            }, 2000);
        } else {
            showAlert('批量操作失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Batch operation error:', error);
        showAlert('批量操作发生错误，请重试', 'danger');
    } finally {
        showLoading(false);
    }
}

// 显示批量操作结果
function showBatchResults(data) {
    let resultHtml = `
        <div class="alert alert-info">
            <h6>操作汇总</h6>
            <p>成功: ${data.success_count}/${data.total_count}</p>
        </div>
        <div class="table-responsive">
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>实例名称</th>
                        <th>状态</th>
                        <th>消息</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    data.results.forEach(result => {
        const statusClass = result.success ? 'text-success' : 'text-danger';
        const statusIcon = result.success ? 'fas fa-check' : 'fas fa-times';
        resultHtml += `
            <tr>
                <td>${result.instance_name}</td>
                <td><i class="${statusIcon} ${statusClass}"></i></td>
                <td class="${statusClass}">${result.success ? result.message : result.error}</td>
            </tr>
        `;
    });
    
    resultHtml += '</tbody></table></div>';
    
    document.getElementById('batchResultContent').innerHTML = resultHtml;
    new bootstrap.Modal(document.getElementById('batchResultModal')).show();
}

// 导出实例到Excel
async function exportInstances() {
    if (!currentClusterId) {
        showAlert('请先选择一个集群', 'warning');
        return;
    }
    
    try {
        showLoading(true);
        
        const exportData = {
            export_all: selectedInstances.size === 0,
            instance_ids: selectedInstances.size > 0 ? Array.from(selectedInstances) : []
        };
        
        const response = await fetch(`/api/instances/export?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(exportData)
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            
            // 从响应头获取文件名
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'instances_export.xlsx';
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="(.+)"/);
                if (filenameMatch) {
                    filename = filenameMatch[1];
                }
            }
            
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showAlert('Excel文件导出成功', 'success');
        } else {
            const data = await response.json();
            showAlert('导出失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Export error:', error);
        showAlert('导出失败，请重试', 'danger');
    } finally {
        showLoading(false);
    }
}

// 重命名实例
function renameInstance(instanceId, currentName) {
    currentRenameInstance = { id: instanceId, name: currentName };
    
    document.getElementById('currentName').value = currentName;
    document.getElementById('newName').value = '';
    
    new bootstrap.Modal(document.getElementById('renameModal')).show();
}

// 确认重命名
async function confirmRename() {
    const newName = document.getElementById('newName').value.trim();
    
    if (!newName) {
        showAlert('请输入新的实例名称', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`/api/instances/${currentRenameInstance.id}/rename?cluster_id=${currentClusterId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: newName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('renameModal')).hide();
            loadInstances(currentPage);
        } else {
            showAlert('重命名失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Rename error:', error);
        showAlert('重命名失败，请重试', 'danger');
    }
}

// 设置销毁时间
function setDestroyTimer(instanceId, instanceName) {
    currentRenameInstance = { id: instanceId, name: instanceName };
    
    document.getElementById('destroyInstanceName').value = instanceName;
    
    // 设置默认时间为1小时后
    const defaultTime = new Date();
    defaultTime.setHours(defaultTime.getHours() + 1);
    document.getElementById('destroyDateTime').value = defaultTime.toISOString().slice(0, 16);
    
    new bootstrap.Modal(document.getElementById('destroyTimerModal')).show();
}

// 确认设置销毁时间
async function confirmDestroyTimer() {
    const destroyDateTime = document.getElementById('destroyDateTime').value;
    
    if (!destroyDateTime) {
        showAlert('请选择销毁时间', 'warning');
        return;
    }
    
    // 检查时间是否在未来
    const destroyDate = new Date(destroyDateTime);
    if (destroyDate <= new Date()) {
        showAlert('销毁时间必须是未来时间', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`/api/instances/${currentRenameInstance.id}/destroy-timer?cluster_id=${currentClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                destroy_at: destroyDate.toISOString()
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert(data.message, 'success');
            bootstrap.Modal.getInstance(document.getElementById('destroyTimerModal')).hide();
            loadInstances(currentPage);
        } else {
            showAlert('设置销毁时间失败: ' + data.error, 'danger');
        }
    } catch (error) {
        console.error('Destroy timer error:', error);
        showAlert('设置销毁时间失败，请重试', 'danger');
    }
}