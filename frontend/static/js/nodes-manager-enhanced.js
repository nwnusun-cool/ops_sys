// 节点管理页面 - 增强版本 JavaScript
console.log('🚀 nodes-manager-enhanced.js 加载成功');

class NodesManager {
  constructor() {
    this.currentCluster = null;
    this.currentStatus = '';
    this.currentRole = '';
    this.searchQuery = '';
    this.currentPage = 1;
    this.itemsPerPage = 20;
    this.selectedNodes = new Set();
    this.nodes = [];
    this.filteredNodes = [];
    this.currentViewMode = 'table';
    this.autoRefreshInterval = null;
    this.stateManager = new K8sStateManager('nodes');
    
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadClusters().then(() => {
      this.restorePageState();
    });
    this.initAutoRefresh();
  }

  // 恢复页面状态
  async restorePageState() {
    const state = this.stateManager.loadState();
    
    if (state.clusterId) {
      await K8sPageHelper.restoreSelectValue('cluster-filter', state.clusterId, 
        (clusterId) => {
          this.currentCluster = clusterId;
          this.loadNodes();
        }
      );
    }

    if (state.filters) {
      if (state.filters.status) {
        K8sPageHelper.restoreSelectValue('status-filter', state.filters.status,
          (status) => {
            this.currentStatus = status;
          }
        );
      }
      if (state.filters.role) {
        K8sPageHelper.restoreSelectValue('role-filter', state.filters.role,
          (role) => {
            this.currentRole = role;
          }
        );
      }
    }
  }

  bindEvents() {
    // 搜索框事件
    const searchInput = document.getElementById('node-search');
    if (searchInput) {
      searchInput.addEventListener('input', 
        this.debounce(this.handleSearch.bind(this), 300)
      );
    }

    // 筛选器事件 - 添加状态保存
    const clusterFilter = document.getElementById('cluster-filter');
    if (clusterFilter) {
      clusterFilter.addEventListener('change', (e) => {
        this.stateManager.updateStateField('clusterId', e.target.value);
        this.handleClusterFilter(e);
      });
    }

    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) {
      statusFilter.addEventListener('change', (e) => {
        const currentState = this.stateManager.loadState();
        const filters = currentState.filters || {};
        filters.status = e.target.value;
        this.stateManager.updateStateField('filters', filters);
        this.handleStatusFilter(e);
      });
    }

    const roleFilter = document.getElementById('role-filter');
    if (roleFilter) {
      roleFilter.addEventListener('change', (e) => {
        const currentState = this.stateManager.loadState();
        const filters = currentState.filters || {};
        filters.role = e.target.value;
        this.stateManager.updateStateField('filters', filters);
        this.handleRoleFilter(e);
      });
    }

    // 视图切换事件
    document.querySelectorAll('input[name="view-mode"]').forEach(radio => {
      radio.addEventListener('change', this.handleViewModeChange.bind(this));
    });

    // 刷新按钮
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', this.handleRefresh.bind(this));
    }

    // 全选复选框
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener('change', this.handleSelectAll.bind(this));
    }

    // 批量操作
    const batchCordonBtn = document.getElementById('batch-cordon-btn');
    if (batchCordonBtn) {
      batchCordonBtn.addEventListener('click', this.handleBatchCordon.bind(this));
    }

    const batchUncordonBtn = document.getElementById('batch-uncordon-btn');
    if (batchUncordonBtn) {
      batchUncordonBtn.addEventListener('click', this.handleBatchUncordon.bind(this));
    }

    const batchDrainBtn = document.getElementById('batch-drain-btn');
    if (batchDrainBtn) {
      batchDrainBtn.addEventListener('click', this.handleBatchDrain.bind(this));
    }

    // 详情面板关闭（现在使用模态框，不需要手动绑定关闭事件）

    // 键盘快捷键
    document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));

    // 表格行点击事件
    document.addEventListener('click', this.handleTableRowClick.bind(this));
  }

  // 防抖函数
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // 加载集群列表
  async loadClusters() {
    try {
      const response = await fetch('/api/k8s/clusters');
      const data = await response.json();
      
      const clusterSelect = document.getElementById('cluster-filter');
      if (clusterSelect && data.success && data.data) {
        clusterSelect.innerHTML = '<option value="">选择集群...</option>';
        data.data.forEach(cluster => {
          const option = document.createElement('option');
          option.value = cluster.id;
          option.textContent = `${cluster.name} (${cluster.cluster_status || 'Unknown'})`;
          clusterSelect.appendChild(option);
        });
      }
    } catch (error) {
      console.error('加载集群失败:', error);
      this.showNotification('加载集群失败', 'error');
    }
  }

  // 加载节点列表
  async loadNodes() {
    if (!this.currentCluster) {
      this.showEmptyState();
      return;
    }

    this.showLoading();
    
    try {
      const params = new URLSearchParams({
        status: this.currentStatus,
        role: this.currentRole,
        page: this.currentPage,
        per_page: this.itemsPerPage
      });
      
      if (this.searchQuery) {
        params.append('search', this.searchQuery);
      }
      
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/nodes?${params}`);
      const data = await response.json();
      
      if (data.success && data.data) {
        this.nodes = data.data;
        this.filterAndDisplayNodes();
        this.updateStatistics();
        this.updatePagination(data.page || 1, data.per_page || this.itemsPerPage, data.total || 0, data.total_pages || 1);
      } else {
        throw new Error(data.message || '加载节点列表失败');
      }
    } catch (error) {
      console.error('加载节点失败:', error);
      this.showNotification('加载节点列表失败: ' + error.message, 'error');
      this.nodes = [];
      this.showEmptyState();
    } finally {
      this.hideLoading();
    }
  }

  // 筛选和显示节点
  filterAndDisplayNodes() {
    // 应用筛选条件
    this.filteredNodes = this.nodes.filter(node => {
      const matchesSearch = !this.searchQuery || 
        node.name.toLowerCase().includes(this.searchQuery.toLowerCase());
      
      return matchesSearch;
    });

    // 显示数据
    if (this.currentViewMode === 'table') {
      this.displayTableView(this.filteredNodes);
    } else {
      this.displayCardView(this.filteredNodes);
    }

    // 更新选择状态
    this.updateBatchActions();
  }

  // 表格视图显示
  displayTableView(nodes) {
    const tbody = document.getElementById('nodes-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (nodes.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="12" class="text-center py-4">
            <i class="fas fa-server fa-3x text-muted mb-3"></i>
            <h5 class="text-muted">暂无节点</h5>
            <p class="text-muted">当前筛选条件下没有找到节点</p>
          </td>
        </tr>
      `;
      return;
    }

    nodes.forEach(node => {
      const row = this.createTableRow(node);
      tbody.appendChild(row);
    });
  }

  // 创建表格行
  createTableRow(node) {
    const row = document.createElement('tr');
    row.dataset.nodeName = node.name;
    
    const isSelected = this.selectedNodes.has(node.name);
    if (isSelected) {
      row.classList.add('selected');
    }

    const statusClass = this.getStatusClass(node.status);
    const createdTime = node.age ? this.parseAge(node.age) : null;
    const timeAgo = createdTime ? this.formatTimeAgo(createdTime) : node.age || '-';
    
    // 计算资源使用百分比
    const cpuPercent = node.resource_usage?.cpu_usage_percent || 0;
    const memoryPercent = node.resource_usage?.memory_usage_percent || 0;
    const podPercent = node.resource_usage?.pod_usage_percent || 0;

    row.innerHTML = `
      <td>
        <input type="checkbox" class="node-checkbox" 
               ${isSelected ? 'checked' : ''} 
               data-node-name="${node.name}">
      </td>
      <td>
        <span class="status-badge ${statusClass}">
          ${this.getStatusText(node.status)}
        </span>
      </td>
      <td>
        <div class="node-name-cell">
          <strong>${node.name}</strong>
          ${node.labels && node.labels['kubernetes.io/hostname'] ? 
            `<small class="text-muted d-block">主机名: ${node.labels['kubernetes.io/hostname']}</small>` : ''}
        </div>
      </td>
      <td>
        <div class="roles-container">
          ${(node.roles || []).map(role => 
            `<span class="role-badge role-${role}">${this.getRoleDisplayName(role)}</span>`
          ).join('')}
        </div>
      </td>
      <td>
        <span class="version-badge">${node.version || 'N/A'}</span>
      </td>
      <td>
        <div class="os-info">
          <small>${node.os_image || 'N/A'}</small><br>
          <small class="text-muted">${node.kernel_version || 'N/A'}</small>
        </div>
      </td>
      <td>
        <span class="runtime-badge">${node.container_runtime || 'N/A'}</span>
      </td>
      <td>
        <div class="ip-info">
          <div><strong>内部:</strong> ${node.internal_ip || 'N/A'}</div>
          ${node.external_ip && node.external_ip !== '<none>' ? 
            `<div><strong>外部:</strong> ${node.external_ip}</div>` : ''}
        </div>
      </td>
      <td>
        <div class="resource-usage">
          <div class="resource-item">
            <small>CPU: ${node.cpu_used || '0m'} (${cpuPercent}%)</small>
            <div class="resource-bar">
              <div class="resource-fill" style="width: ${cpuPercent}%"></div>
            </div>
          </div>
          <div class="resource-item mt-1">
            <small>内存: ${node.memory_used || '0Mi'} (${memoryPercent}%)</small>
            <div class="resource-bar">
              <div class="resource-fill" style="width: ${memoryPercent}%"></div>
            </div>
          </div>
        </div>
      </td>
      <td>
        <div class="pod-info">
          <div><strong>${node.pod_count || 0}</strong> / ${node.capacity?.pods || 'N/A'}</div>
          <div class="pod-breakdown">
            <small>运行: ${node.running_pods || 0}</small>
            ${node.pending_pods ? `<small>等待: ${node.pending_pods}</small>` : ''}
            ${node.failed_pods ? `<small class="text-danger">失败: ${node.failed_pods}</small>` : ''}
          </div>
          <div class="resource-bar mt-1">
            <div class="resource-fill" style="width: ${podPercent}%"></div>
          </div>
        </div>
      </td>
      <td>
        <small title="${node.age || ''}" class="time-ago">
          ${timeAgo}
        </small>
      </td>
      <td>
        <div class="action-buttons">
          <button class="btn btn-outline-primary btn-sm" 
                  onclick="nodesManager.showNodeDetail('${node.name}')"
                  title="查看详情">
            <i class="fas fa-eye"></i>
          </button>
          ${node.status === 'Ready' ? `
            <button class="btn btn-outline-warning btn-sm" 
                    onclick="nodesManager.cordonNode('${node.name}')"
                    title="封锁节点">
              <i class="fas fa-ban"></i>
            </button>
          ` : ''}
          ${node.status === 'Ready' ? `
            <button class="btn btn-outline-danger btn-sm" 
                    onclick="nodesManager.drainNode('${node.name}')"
                    title="驱逐Pod">
              <i class="fas fa-eject"></i>
            </button>
          ` : `
            <button class="btn btn-outline-success btn-sm" 
                    onclick="nodesManager.uncordonNode('${node.name}')"
                    title="解除封锁">
              <i class="fas fa-play"></i>
            </button>
          `}
        </div>
      </td>
    `;

    return row;
  }

  // 卡片视图显示
  displayCardView(nodes) {
    const container = document.getElementById('nodes-cards-container');
    if (!container) return;

    container.innerHTML = '';

    if (nodes.length === 0) {
      container.innerHTML = `
        <div class="col-12">
          <div class="empty-state">
            <i class="fas fa-server fa-3x text-muted"></i>
            <h5>暂无节点</h5>
            <p>当前筛选条件下没有找到节点</p>
          </div>
        </div>
      `;
      return;
    }

    nodes.forEach(node => {
      const card = this.createNodeCard(node);
      container.appendChild(card);
    });
  }

  // 创建节点卡片
  createNodeCard(node) {
    const card = document.createElement('div');
    card.className = 'node-card';
    card.dataset.nodeName = node.name;
    
    const isSelected = this.selectedNodes.has(node.name);
    if (isSelected) {
      card.classList.add('selected');
    }

    const statusClass = this.getStatusClass(node.status);
    const createdTime = node.age ? this.parseAge(node.age) : null;
    const timeAgo = createdTime ? this.formatTimeAgo(createdTime) : node.age || '-';
    
    const cpuPercent = node.resource_usage?.cpu_usage_percent || 0;
    const memoryPercent = node.resource_usage?.memory_usage_percent || 0;
    const podPercent = node.resource_usage?.pod_usage_percent || 0;

    card.innerHTML = `
      <div class="card-header d-flex justify-content-between align-items-center">
        <div class="node-info">
          <h6 class="mb-1">${node.name}</h6>
          <small class="text-muted">${node.internal_ip || 'N/A'}</small>
        </div>
        <div class="card-actions">
          <input type="checkbox" class="node-checkbox me-2" 
                 ${isSelected ? 'checked' : ''} 
                 data-node-name="${node.name}">
          <span class="status-badge ${statusClass}">
            ${this.getStatusText(node.status)}
          </span>
        </div>
      </div>
      
      <div class="card-body">
        <div class="node-details">
          <div class="detail-item mb-2">
            <small class="text-muted">角色:</small>
            <div class="roles-container">
              ${(node.roles || []).map(role => 
                `<span class="role-badge role-${role}">${this.getRoleDisplayName(role)}</span>`
              ).join('')}
            </div>
          </div>
          <div class="detail-item mb-2">
            <small class="text-muted">版本:</small>
            <span>${node.version || 'N/A'}</span>
          </div>
          <div class="detail-item mb-2">
            <small class="text-muted">容器运行时:</small>
            <span>${node.container_runtime || 'N/A'}</span>
          </div>
          <div class="detail-item mb-2">
            <small class="text-muted">运行时间:</small>
            <span class="time-ago">${timeAgo}</span>
          </div>
        </div>
        
        <div class="resource-usage mt-3">
          <div class="resource-item mb-2">
            <div class="d-flex justify-content-between">
              <small class="text-muted">CPU使用率</small>
              <small>${cpuPercent}%</small>
            </div>
            <div class="resource-bar">
              <div class="resource-fill" style="width: ${cpuPercent}%"></div>
            </div>
          </div>
          
          <div class="resource-item mb-2">
            <div class="d-flex justify-content-between">
              <small class="text-muted">内存使用率</small>
              <small>${memoryPercent}%</small>
            </div>
            <div class="resource-bar">
              <div class="resource-fill" style="width: ${memoryPercent}%"></div>
            </div>
          </div>
          
          <div class="resource-item">
            <div class="d-flex justify-content-between">
              <small class="text-muted">Pod使用率</small>
              <small>${node.pod_count || 0}/${node.capacity?.pods || 'N/A'} (${podPercent}%)</small>
            </div>
            <div class="resource-bar">
              <div class="resource-fill" style="width: ${podPercent}%"></div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="card-footer">
        <div class="action-buttons w-100 d-flex gap-2">
          <button class="btn btn-outline-primary btn-sm flex-fill" 
                  onclick="nodesManager.showNodeDetail('${node.name}')">
            <i class="fas fa-eye"></i> 详情
          </button>
          ${node.status === 'Ready' ? `
            <button class="btn btn-outline-warning btn-sm flex-fill" 
                    onclick="nodesManager.cordonNode('${node.name}')">
              <i class="fas fa-ban"></i> 封锁
            </button>
            <button class="btn btn-outline-danger btn-sm flex-fill" 
                    onclick="nodesManager.drainNode('${node.name}')">
              <i class="fas fa-eject"></i> 驱逐
            </button>
          ` : `
            <button class="btn btn-outline-success btn-sm flex-fill" 
                    onclick="nodesManager.uncordonNode('${node.name}')">
              <i class="fas fa-play"></i> 解封
            </button>
          `}
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (!e.target.matches('.node-checkbox, button, .btn, .btn *')) {
        this.showNodeDetail(node.name);
      }
    });

    return card;
  }

  // 更新统计信息
  updateStatistics() {
    const stats = {
      ready: 0,
      notReady: 0,
      master: 0,
      total: this.nodes.length
    };

    this.nodes.forEach(node => {
      // 统计状态
      if (node.status === 'Ready') {
        stats.ready++;
      } else {
        stats.notReady++;
      }
      
      // 统计角色
      if (node.roles && (node.roles.includes('master') || node.roles.includes('control-plane'))) {
        stats.master++;
      }
    });

    // 动画更新统计数字
    this.animateNumber('ready-nodes-count', stats.ready);
    this.animateNumber('not-ready-nodes-count', stats.notReady);
    this.animateNumber('master-nodes-count', stats.master);
    this.animateNumber('total-nodes-count', stats.total);
  }

  // 数字动画效果
  animateNumber(elementId, targetValue) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const currentValue = parseInt(element.textContent) || 0;
    const step = (targetValue - currentValue) / 20;
    
    let current = currentValue;
    const timer = setInterval(() => {
      current += step;
      if ((step > 0 && current >= targetValue) || 
          (step < 0 && current <= targetValue)) {
        current = targetValue;
        clearInterval(timer);
      }
      element.textContent = Math.round(current);
    }, 50);
  }

  // 事件处理函数
  handleSearch(event) {
    this.searchQuery = event.target.value;
    this.currentPage = 1;
    this.loadNodes();
  }

  handleClusterFilter(event) {
    this.currentCluster = event.target.value;
    if (this.currentCluster) {
      this.loadNodes();
    } else {
      this.showEmptyState();
    }
  }

  handleStatusFilter(event) {
    this.currentStatus = event.target.value;
    this.currentPage = 1;
    this.loadNodes();
  }

  handleRoleFilter(event) {
    this.currentRole = event.target.value;
    this.currentPage = 1;
    this.loadNodes();
  }

  handleViewModeChange(event) {
    this.currentViewMode = event.target.id === 'table-view' ? 'table' : 'card';
    
    const tableContent = document.getElementById('table-view-content');
    const cardContent = document.getElementById('card-view-content');
    
    if (this.currentViewMode === 'table') {
      if (tableContent) tableContent.style.display = 'block';
      if (cardContent) cardContent.style.display = 'none';
      this.displayTableView(this.filteredNodes);
    } else {
      if (tableContent) tableContent.style.display = 'none';
      if (cardContent) cardContent.style.display = 'block';
      this.displayCardView(this.filteredNodes);
    }
  }

  handleRefresh() {
    const refreshBtn = document.getElementById('refresh-btn');
    const icon = refreshBtn?.querySelector('i');
    
    if (icon) icon.classList.add('fa-spin');
    
    this.loadNodes().finally(() => {
      setTimeout(() => {
        if (icon) icon.classList.remove('fa-spin');
      }, 500);
    });
    
    // 通知自动刷新管理器
    if (typeof notifyManualRefresh === 'function') {
      notifyManualRefresh();
    }
  }

  handleSelectAll(event) {
    const checkboxes = document.querySelectorAll('.node-checkbox');
    const isChecked = event.target.checked;
    
    checkboxes.forEach(checkbox => {
      checkbox.checked = isChecked;
      const nodeName = checkbox.dataset.nodeName;
      
      if (isChecked) {
        this.selectedNodes.add(nodeName);
      } else {
        this.selectedNodes.delete(nodeName);
      }
    });
    
    this.updateTableRowSelection();
    this.updateBatchActions();
  }

  handleTableRowClick(event) {
    if (event.target.matches('.node-checkbox')) {
      const nodeName = event.target.dataset.nodeName;
      const isChecked = event.target.checked;
      
      if (isChecked) {
        this.selectedNodes.add(nodeName);
      } else {
        this.selectedNodes.delete(nodeName);
      }
      
      this.updateTableRowSelection();
      this.updateBatchActions();
    }
  }

  // 更新表格行选择状态
  updateTableRowSelection() {
    document.querySelectorAll('.nodes-table tbody tr, .node-card').forEach(element => {
      const checkbox = element.querySelector('.node-checkbox');
      if (checkbox) {
        if (checkbox.checked) {
          element.classList.add('selected');
        } else {
          element.classList.remove('selected');
        }
      }
    });
  }

  // 更新批量操作
  updateBatchActions() {
    const batchActions = document.getElementById('batch-actions');
    const selectedCount = document.getElementById('selected-count');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    
    if (selectedCount) selectedCount.textContent = this.selectedNodes.size;
    
    if (batchActions) {
      if (this.selectedNodes.size > 0) {
        batchActions.style.display = 'flex';
      } else {
        batchActions.style.display = 'none';
      }
    }
    
    // 更新全选复选框状态
    if (selectAllCheckbox) {
      const totalCheckboxes = document.querySelectorAll('.node-checkbox').length;
      if (this.selectedNodes.size === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
      } else if (this.selectedNodes.size === totalCheckboxes) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = true;
      } else {
        selectAllCheckbox.indeterminate = true;
      }
    }
  }

  // 批量操作处理
  async handleBatchCordon() {
    if (this.selectedNodes.size === 0) return;
    
    if (!await this.showConfirmDialog('批量封锁确认', `确定要封锁选中的 ${this.selectedNodes.size} 个节点吗？`)) {
      return;
    }
    
    await this.executeBatchOperation('cordon', '封锁');
  }

  async handleBatchUncordon() {
    if (this.selectedNodes.size === 0) return;
    
    if (!await this.showConfirmDialog('批量解封确认', `确定要解除封锁选中的 ${this.selectedNodes.size} 个节点吗？`)) {
      return;
    }
    
    await this.executeBatchOperation('uncordon', '解封');
  }

  async handleBatchDrain() {
    if (this.selectedNodes.size === 0) return;
    
    if (!await this.showConfirmDialog('批量驱逐确认', `确定要驱逐选中的 ${this.selectedNodes.size} 个节点上的所有Pod吗？此操作可能会影响服务运行。`)) {
      return;
    }
    
    await this.executeBatchOperation('drain', '驱逐');
  }

  async executeBatchOperation(operation, operationName) {
    this.showLoading();
    const operationTasks = Array.from(this.selectedNodes).map(nodeName => {
      return this.executeNodeOperation(nodeName, operation);
    });
    
    try {
      const results = await Promise.allSettled(operationTasks);
      const successful = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      
      if (failed === 0) {
        this.showNotification(`成功${operationName} ${successful} 个节点`, 'success');
      } else {
        this.showNotification(`${operationName}完成: 成功 ${successful} 个，失败 ${failed} 个`, 'warning');
      }
      
      this.selectedNodes.clear();
      this.loadNodes();
    } catch (error) {
      this.showNotification(`批量${operationName}失败: ` + error.message, 'error');
    } finally {
      this.hideLoading();
    }
  }

  // 节点操作方法
  async cordonNode(nodeName) {
    if (!await this.showConfirmDialog('封锁确认', `确定要封锁节点 "${nodeName}" 吗？封锁后该节点将不会调度新的Pod。`)) {
      return;
    }

    try {
      await this.executeNodeOperation(nodeName, 'cordon');
      this.showNotification('节点封锁成功', 'success');
      this.loadNodes();
    } catch (error) {
      this.showNotification('节点封锁失败: ' + error.message, 'error');
    }
  }

  async uncordonNode(nodeName) {
    if (!await this.showConfirmDialog('解封确认', `确定要解除节点 "${nodeName}" 的封锁吗？`)) {
      return;
    }

    try {
      await this.executeNodeOperation(nodeName, 'uncordon');
      this.showNotification('节点解封成功', 'success');
      this.loadNodes();
    } catch (error) {
      this.showNotification('节点解封失败: ' + error.message, 'error');
    }
  }

  async drainNode(nodeName) {
    if (!await this.showConfirmDialog('驱逐确认', `确定要驱逐节点 "${nodeName}" 上的所有Pod吗？此操作会将Pod重新调度到其他节点。`)) {
      return;
    }

    try {
      await this.executeNodeOperation(nodeName, 'drain');
      this.showNotification('节点驱逐成功', 'success');
      this.loadNodes();
    } catch (error) {
      this.showNotification('节点驱逐失败: ' + error.message, 'error');
    }
  }

  async executeNodeOperation(nodeName, operation) {
    const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/nodes/${nodeName}/${operation}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({})
    });
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.message || `${operation}操作失败`);
    }
    return data;
  }

  // 显示节点详情
  async showNodeDetail(nodeName) {
    if (!this.currentCluster || !nodeName) return;

    const modal = document.getElementById('node-detail-modal');
    const titleElement = document.getElementById('detail-node-name');
    const contentElement = document.getElementById('node-detail-modal-body');
    
    if (titleElement) titleElement.textContent = nodeName;
    if (contentElement) {
      contentElement.innerHTML = '<div class="loading-container text-center p-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-3">加载节点详情中...</p></div>';
    }
    
    // 显示模态框
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
    
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/nodes/${nodeName}`);
      const data = await response.json();
      
      if (data.success && data.data && contentElement) {
        contentElement.innerHTML = this.generateNodeDetailHTML(data.data);
      } else {
        throw new Error(data.message || '获取节点详情失败');
      }
    } catch (error) {
      if (contentElement) {
        contentElement.innerHTML = `
          <div class="alert alert-danger">
            <i class="fas fa-exclamation-triangle"></i>
            加载节点详情失败: ${error.message}
          </div>
        `;
      }
    }
  }

  // 生成节点详情HTML
  generateNodeDetailHTML(node) {
    const cpuPercent = node.resource_usage?.cpu_usage_percent || 0;
    const memoryPercent = node.resource_usage?.memory_usage_percent || 0;
    const podPercent = node.resource_usage?.pod_usage_percent || 0;

    return `
      <div class="node-detail-content">
        <!-- 基本信息 -->
        <div class="detail-section">
          <h6 class="section-title">
            <i class="fas fa-info-circle"></i> 基本信息
          </h6>
          <div class="detail-grid">
            <div class="detail-item">
              <label>节点名称:</label>
              <span>${node.name}</span>
            </div>
            <div class="detail-item">
              <label>状态:</label>
              <span class="status-badge ${this.getStatusClass(node.status)}">
                ${this.getStatusText(node.status)}
              </span>
            </div>
            <div class="detail-item">
              <label>角色:</label>
              <div class="roles-container">
                ${(node.roles || []).map(role => 
                  `<span class="role-badge role-${role}">${this.getRoleDisplayName(role)}</span>`
                ).join('')}
              </div>
            </div>
            <div class="detail-item">
              <label>K8s版本:</label>
              <span class="version-badge">${node.version || 'N/A'}</span>
            </div>
            <div class="detail-item">
              <label>运行时间:</label>
              <span>${node.age || 'N/A'}</span>
            </div>
          </div>
        </div>

        <!-- 网络信息 -->
        <div class="detail-section">
          <h6 class="section-title">
            <i class="fas fa-network-wired"></i> 网络信息
          </h6>
          <div class="detail-grid">
            <div class="detail-item">
              <label>内部IP:</label>
              <span class="ip-address">${node.internal_ip || 'N/A'}</span>
            </div>
            <div class="detail-item">
              <label>外部IP:</label>
              <span class="ip-address">${node.external_ip && node.external_ip !== '<none>' ? node.external_ip : 'N/A'}</span>
            </div>
          </div>
        </div>

        <!-- 系统信息 -->
        <div class="detail-section">
          <h6 class="section-title">
            <i class="fas fa-desktop"></i> 系统信息
          </h6>
          <div class="detail-grid">
            <div class="detail-item">
              <label>操作系统:</label>
              <span>${node.os_image || 'N/A'}</span>
            </div>
            <div class="detail-item">
              <label>内核版本:</label>
              <span>${node.kernel_version || 'N/A'}</span>
            </div>
            <div class="detail-item">
              <label>容器运行时:</label>
              <span class="runtime-badge">${node.container_runtime || 'N/A'}</span>
            </div>
          </div>
        </div>

        <!-- 资源容量 -->
        <div class="detail-section">
          <h6 class="section-title">
            <i class="fas fa-server"></i> 资源容量
          </h6>
          <div class="resource-capacity-grid">
            <div class="capacity-item">
              <div class="capacity-header">
                <span class="capacity-label">CPU</span>
                <span class="capacity-value">${node.capacity?.cpu || 'N/A'}</span>
              </div>
              <div class="capacity-detail">
                <div>可分配: ${node.allocatable?.cpu || 'N/A'}</div>
                <div>已使用: ${node.cpu_used || '0m'} (${cpuPercent}%)</div>
                <div class="resource-bar mt-1">
                  <div class="resource-fill" style="width: ${cpuPercent}%"></div>
                </div>
              </div>
            </div>
            
            <div class="capacity-item">
              <div class="capacity-header">
                <span class="capacity-label">内存</span>
                <span class="capacity-value">${node.capacity?.memory || 'N/A'}</span>
              </div>
              <div class="capacity-detail">
                <div>可分配: ${node.allocatable?.memory || 'N/A'}</div>
                <div>已使用: ${node.memory_used || '0Mi'} (${memoryPercent}%)</div>
                <div class="resource-bar mt-1">
                  <div class="resource-fill" style="width: ${memoryPercent}%"></div>
                </div>
              </div>
            </div>
            
            <div class="capacity-item">
              <div class="capacity-header">
                <span class="capacity-label">Pod容量</span>
                <span class="capacity-value">${node.capacity?.pods || 'N/A'}</span>
              </div>
              <div class="capacity-detail">
                <div>当前Pod: ${node.pod_count || 0}</div>
                <div>运行中: ${node.running_pods || 0}</div>
                ${node.pending_pods ? `<div>等待中: ${node.pending_pods}</div>` : ''}
                ${node.failed_pods ? `<div class="text-danger">失败: ${node.failed_pods}</div>` : ''}
                <div class="resource-bar mt-1">
                  <div class="resource-fill" style="width: ${podPercent}%"></div>
                </div>
              </div>
            </div>
            
            <div class="capacity-item">
              <div class="capacity-header">
                <span class="capacity-label">存储</span>
                <span class="capacity-value">${node.capacity?.storage || 'N/A'}</span>
              </div>
              <div class="capacity-detail">
                <div>可分配: ${node.allocatable?.storage || 'N/A'}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 标签 -->
        ${node.labels && Object.keys(node.labels).length > 0 ? `
          <div class="detail-section">
            <h6 class="section-title">
              <i class="fas fa-tags"></i> 节点标签
            </h6>
            <div class="labels-container">
              ${Object.entries(node.labels).map(([key, value]) => 
                `<span class="label-badge" title="${key}: ${value}">${key}: ${value}</span>`
              ).join('')}
            </div>
          </div>
        ` : ''}

        <!-- 注解 -->
        ${node.annotations && Object.keys(node.annotations).length > 0 ? `
          <div class="detail-section">
            <h6 class="section-title">
              <i class="fas fa-sticky-note"></i> 注解信息
            </h6>
            <div class="annotations-list">
              ${Object.entries(node.annotations).slice(0, 5).map(([key, value]) => `
                <div class="annotation-item">
                  <strong>${key}:</strong> ${value}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- 条件状态 -->
        ${node.conditions && node.conditions.length > 0 ? `
          <div class="detail-section">
            <h6 class="section-title">
              <i class="fas fa-heartbeat"></i> 节点条件
            </h6>
            <div class="conditions-list">
              ${node.conditions.map(condition => `
                <div class="condition-item">
                  <div class="condition-header">
                    <span class="condition-type">${condition.type}</span>
                    <span class="condition-status status-${condition.status?.toLowerCase()}">
                      ${condition.status}
                    </span>
                  </div>
                  <div class="condition-details">
                    <div><strong>原因:</strong> ${condition.reason || 'N/A'}</div>
                    <div><strong>消息:</strong> ${condition.message || 'N/A'}</div>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        <!-- 操作按钮 -->
        <div class="detail-section">
          <div class="d-grid gap-2">
            ${node.status === 'Ready' ? `
              <button class="btn btn-outline-warning" 
                      onclick="nodesManager.cordonNode('${node.name}')">
                <i class="fas fa-ban"></i> 封锁节点
              </button>
              <button class="btn btn-outline-danger" 
                      onclick="nodesManager.drainNode('${node.name}')">
                <i class="fas fa-eject"></i> 驱逐Pod
              </button>
            ` : `
              <button class="btn btn-outline-success" 
                      onclick="nodesManager.uncordonNode('${node.name}')">
                <i class="fas fa-play"></i> 解除封锁
              </button>
            `}
          </div>
        </div>
      </div>
    `;
  }

  // 键盘快捷键处理
  handleKeyboardShortcuts(event) {
    // ESC 键关闭详情模态框
    if (event.key === 'Escape') {
      const modal = document.getElementById('node-detail-modal');
      if (modal && modal.classList.contains('show')) {
        bootstrap.Modal.getInstance(modal)?.hide();
      }
    }
    
    // Ctrl/Cmd + F 聚焦搜索框
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
      event.preventDefault();
      const searchInput = document.getElementById('node-search');
      if (searchInput) searchInput.focus();
    }
    
    // Ctrl/Cmd + R 刷新
    if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
      event.preventDefault();
      this.handleRefresh();
    }
  }

  // 更新分页
  updatePagination(page, perPage, total, totalPages) {
    this.currentPage = page;
    
    const paginationInfo = document.querySelector('.pagination-info');
    const paginationControls = document.getElementById('pagination-controls');
    
    if (paginationInfo) {
      const startIndex = (page - 1) * perPage + 1;
      const endIndex = Math.min(startIndex + perPage - 1, total);
      
      document.getElementById('items-range').textContent = 
        total > 0 ? `${startIndex}-${endIndex}` : '0-0';
      document.getElementById('total-items').textContent = total;
    }
    
    // 生成分页控件
    if (paginationControls) {
      paginationControls.innerHTML = this.generatePaginationHTML(totalPages);
    }
  }

  generatePaginationHTML(totalPages) {
    if (totalPages <= 1) return '';
    
    let html = '';
    const current = this.currentPage;
    
    // 上一页
    html += `
      <li class="page-item ${current === 1 ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="nodesManager.goToPage(${current - 1})">上一页</a>
      </li>
    `;
    
    // 页码
    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= current - 2 && i <= current + 2)) {
        html += `
          <li class="page-item ${i === current ? 'active' : ''}">
            <a class="page-link" href="#" onclick="nodesManager.goToPage(${i})">${i}</a>
          </li>
        `;
      } else if (i === current - 3 || i === current + 3) {
        html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
      }
    }
    
    // 下一页
    html += `
      <li class="page-item ${current === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="nodesManager.goToPage(${current + 1})">下一页</a>
      </li>
    `;
    
    return html;
  }

  goToPage(page) {
    const totalPages = Math.ceil(this.nodes.length / this.itemsPerPage);
    if (page >= 1 && page <= totalPages) {
      this.currentPage = page;
      this.loadNodes();
    }
  }

  // 工具函数
  getStatusClass(status) {
    switch (status?.toLowerCase()) {
      case 'ready':
        return 'status-ready';
      case 'notready':
        return 'status-not-ready';
      case 'schedulingdisabled':
        return 'status-disabled';
      default:
        return 'status-unknown';
    }
  }

  getStatusText(status) {
    const statusMap = {
      'ready': '就绪',
      'notready': '未就绪',
      'unknown': '未知',
      'schedulingdisabled': '调度禁用'
    };
    return statusMap[status?.toLowerCase()] || status;
  }

  getRoleDisplayName(role) {
    const roleMap = {
      'master': '控制节点',
      'control-plane': '控制节点', 
      'worker': '工作节点',
      'node': '节点'
    };
    return roleMap[role] || role;
  }

  parseAge(ageString) {
    if (!ageString) return null;
    
    // 简单的年龄解析，支持 "25d", "2h", "30m" 等格式
    const now = new Date();
    const matches = ageString.match(/(\d+)([dhm])/);
    if (matches) {
      const value = parseInt(matches[1]);
      const unit = matches[2];
      
      switch (unit) {
        case 'd':
          return new Date(now.getTime() - value * 24 * 60 * 60 * 1000);
        case 'h':
          return new Date(now.getTime() - value * 60 * 60 * 1000);
        case 'm':
          return new Date(now.getTime() - value * 60 * 1000);
      }
    }
    
    return null;
  }

  formatTimeAgo(date) {
    if (!date) return '-';
    
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    
    if (diffInSeconds < 60) return '刚刚';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}分钟前`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}小时前`;
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)}天前`;
    
    return date.toLocaleDateString();
  }

  // UI 辅助方法
  showLoading() {
    // 可以添加全局加载指示器
    console.log('Loading...');
  }

  hideLoading() {
    // 隐藏全局加载指示器
    console.log('Loading complete');
  }

  showEmptyState() {
    const tableContent = document.getElementById('table-view-content');
    const cardContent = document.getElementById('card-view-content');
    
    if (this.currentViewMode === 'table') {
      this.displayTableView([]);
    } else {
      this.displayCardView([]);
    }
  }

  showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // 自动移除
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, type === 'error' ? 10000 : 5000);
  }

  async showConfirmDialog(title, message) {
    // 简单的确认对话框，可以替换为更美观的模态框
    return confirm(`${title}\n\n${message}`);
  }

  // 初始化自动刷新
  initAutoRefresh() {
    // 使用全局自动刷新组件
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        if (this.currentCluster) {
          this.loadNodes();
        }
      }, {
        defaultInterval: 30000,
        storageKey: 'autoRefreshSettings_nodes'
      });
    }
  }

  // 自动刷新（保留兼容性）
  startAutoRefresh() {
    this.initAutoRefresh();
  }

  stopAutoRefresh() {
    if (this.autoRefreshManager) {
      this.autoRefreshManager.destroy();
      this.autoRefreshManager = null;
    }
  }
}

// 初始化节点管理器
let nodesManager;
document.addEventListener('DOMContentLoaded', () => {
  nodesManager = new NodesManager();
});

// 全局函数（供HTML中的onclick使用）
if (typeof window !== 'undefined') {
  window.nodesManager = {
    showNodeDetail: (nodeName) => nodesManager?.showNodeDetail(nodeName),
    cordonNode: (nodeName) => nodesManager?.cordonNode(nodeName),
    uncordonNode: (nodeName) => nodesManager?.uncordonNode(nodeName),
    drainNode: (nodeName) => nodesManager?.drainNode(nodeName),
    goToPage: (page) => nodesManager?.goToPage(page)
  };
}