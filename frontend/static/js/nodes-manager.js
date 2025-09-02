// 节点管理功能
class NodesManager {
    constructor() {
        this.init();
    }

    init() {
        this.loadNodes();
        this.bindEvents();
    }

    async loadNodes() {
        try {
            const response = await fetch('/api/k8s/nodes');
            if (response.ok) {
                const nodes = await response.json();
                this.renderNodes(nodes);
            } else {
                console.error('获取节点信息失败');
                this.showError('获取节点信息失败');
            }
        } catch (error) {
            console.error('获取节点信息出错:', error);
            this.showError('网络错误，请检查连接');
        }
    }

    renderNodes(nodes) {
        const tbody = document.getElementById('nodes-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        
        if (nodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">暂无节点信息</td></tr>';
            return;
        }

        nodes.forEach(node => {
            const row = this.createNodeRow(node);
            tbody.appendChild(row);
        });
    }

    createNodeRow(node) {
        const row = document.createElement('tr');
        
        const statusClass = this.getStatusClass(node.status);
        const statusText = this.getStatusText(node.status);
        
        row.innerHTML = `
            <td>${node.name || 'N/A'}</td>
            <td>${node.role || 'N/A'}</td>
            <td>${node.version || 'N/A'}</td>
            <td>${node.internalIP || 'N/A'}</td>
            <td>${node.externalIP || 'N/A'}</td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>
                <button class="btn btn-sm btn-info" onclick="nodesManager.viewNodeDetails('${node.name}')">
                    <i class="fas fa-eye"></i> 详情
                </button>
            </td>
        `;
        
        return row;
    }

    getStatusClass(status) {
        const statusMap = {
            'Ready': 'bg-success',
            'NotReady': 'bg-danger',
            'Unknown': 'bg-warning',
            'SchedulingDisabled': 'bg-secondary'
        };
        return statusMap[status] || 'bg-secondary';
    }

    getStatusText(status) {
        const statusMap = {
            'Ready': '就绪',
            'NotReady': '未就绪',
            'Unknown': '未知',
            'SchedulingDisabled': '调度禁用'
        };
        return statusMap[status] || status;
    }

    async viewNodeDetails(nodeName) {
        try {
            const response = await fetch(`/api/k8s/nodes/${nodeName}`);
            if (response.ok) {
                const nodeDetails = await response.json();
                this.showNodeDetailsModal(nodeDetails);
            } else {
                this.showError('获取节点详情失败');
            }
        } catch (error) {
            console.error('获取节点详情出错:', error);
            this.showError('网络错误');
        }
    }

    showNodeDetailsModal(nodeDetails) {
        // 创建模态框显示节点详情
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'nodeDetailsModal';
        
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">节点详情: ${nodeDetails.name}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h6>基本信息</h6>
                                <table class="table table-sm">
                                    <tr><td>名称:</td><td>${nodeDetails.name}</td></tr>
                                    <tr><td>角色:</td><td>${nodeDetails.role || 'N/A'}</td></tr>
                                    <tr><td>版本:</td><td>${nodeDetails.version || 'N/A'}</td></tr>
                                    <tr><td>状态:</td><td>${nodeDetails.status || 'N/A'}</td></tr>
                                </table>
                            </div>
                            <div class="col-md-6">
                                <h6>网络信息</h6>
                                <table class="table table-sm">
                                    <tr><td>内部IP:</td><td>${nodeDetails.internalIP || 'N/A'}</td></tr>
                                    <tr><td>外部IP:</td><td>${nodeDetails.externalIP || 'N/A'}</td></tr>
                                </table>
                            </div>
                        </div>
                        <div class="row mt-3">
                            <div class="col-12">
                                <h6>资源信息</h6>
                                <table class="table table-sm">
                                    <tr><td>CPU容量:</td><td>${nodeDetails.cpuCapacity || 'N/A'}</td></tr>
                                    <tr><td>内存容量:</td><td>${nodeDetails.memoryCapacity || 'N/A'}</td></tr>
                                    <tr><td>存储容量:</td><td>${nodeDetails.storageCapacity || 'N/A'}</td></tr>
                                </table>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    showError(message) {
        // 显示错误信息
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container');
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }

    bindEvents() {
        // 绑定刷新按钮事件
        const refreshBtn = document.getElementById('refresh-nodes');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadNodes());
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.nodesManager = new NodesManager();
}); 