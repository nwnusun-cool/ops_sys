// Pod管理页面 - KubeSphere风格 JavaScript
console.log('🚀 pods-manager.js 加载成功');

class PodManager {
  constructor() {
    this.currentCluster = null;
    this.currentNamespace = '';
    this.currentStatus = '';
    this.searchQuery = '';
    this.currentPage = 1;
    this.itemsPerPage = 20;
    this.totalPages = 1;
    this.selectedPods = new Set();
    this.pods = [];
    this.filteredPods = [];
    this.currentViewMode = 'table';
    this.autoRefreshManager = null;
    this.stateManager = new K8sStateManager('pods');
    
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
          this.loadNamespaces(clusterId).then(() => {
            if (state.namespace) {
              K8sPageHelper.restoreSelectValue('namespace-filter', state.namespace,
                (namespace) => {
                  this.currentNamespace = namespace;
                  this.loadPods();
                }
              );
            } else {
              this.loadPods();
            }
          });
        }
      );
    }

    if (state.filters && state.filters.status) {
      K8sPageHelper.restoreSelectValue('status-filter', state.filters.status,
        (status) => {
          this.currentStatus = status;
        }
      );
    }
  }

  bindEvents() {
    // 搜索框事件
    const searchInput = document.getElementById('pod-search');
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

    const namespaceFilter = document.getElementById('namespace-filter');
    if (namespaceFilter) {
      namespaceFilter.addEventListener('change', (e) => {
        this.stateManager.updateStateField('namespace', e.target.value);
        this.handleNamespaceFilter(e);
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
    const batchDeleteBtn = document.getElementById('batch-delete-btn');
    if (batchDeleteBtn) {
      batchDeleteBtn.addEventListener('click', this.handleBatchDelete.bind(this));
    }

    // 详情面板关闭
    const closeDetailPanel = document.getElementById('close-detail-panel');
    if (closeDetailPanel) {
      closeDetailPanel.addEventListener('click', this.closeDetailPanel.bind(this));
    }

    // YAML查看器事件
    const copyYamlBtn = document.getElementById('copy-yaml-btn');
    if (copyYamlBtn) {
      copyYamlBtn.addEventListener('click', this.copyYamlToClipboard.bind(this));
    }

    const downloadYamlBtn = document.getElementById('download-yaml-btn');
    if (downloadYamlBtn) {
      downloadYamlBtn.addEventListener('click', this.downloadYaml.bind(this));
    }

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

  // 加载命名空间列表
  async loadNamespaces(clusterId) {
    try {
      const response = await fetch(`/api/k8s/clusters/${clusterId}/namespaces`);
      const data = await response.json();
      
      const namespaceSelect = document.getElementById('namespace-filter');
      if (namespaceSelect && data.success && data.data) {
        namespaceSelect.innerHTML = '<option value="">所有命名空间</option>';
        data.data.forEach(ns => {
          const option = document.createElement('option');
          option.value = ns.name;
          option.textContent = ns.name;
          namespaceSelect.appendChild(option);
        });
      }
    } catch (error) {
      console.error('加载命名空间失败:', error);
    }
  }

  // 加载Pod列表
  async loadPods() {
    if (!this.currentCluster) {
      this.showEmptyState();
      return;
    }

    this.showLoading();
    
    try {
      const params = new URLSearchParams({
        namespace: this.currentNamespace,
        status: this.currentStatus,
        page: this.currentPage,
        per_page: this.itemsPerPage
      });
      
      if (this.searchQuery) {
        params.append('name', this.searchQuery);
      }
      
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/pods?${params}`);
      const data = await response.json();
      
      if (data.success && data.data) {
        this.pods = data.data;
        this.filterAndDisplayPods();
        this.updateStatistics();
        this.updatePagination(data.page || 1, data.per_page || this.itemsPerPage, data.total || 0, data.total_pages || 1);
      } else {
        throw new Error(data.message || '加载Pod列表失败');
      }
    } catch (error) {
      console.error('加载Pod失败:', error);
      this.showNotification('加载Pod列表失败: ' + error.message, 'error');
      this.pods = [];
      this.showEmptyState();
    } finally {
      this.hideLoading();
    }
  }

  // 筛选和显示Pod
  filterAndDisplayPods() {
    // 应用筛选条件
    this.filteredPods = this.pods.filter(pod => {
      const matchesSearch = !this.searchQuery || 
        pod.name.toLowerCase().includes(this.searchQuery.toLowerCase());
      
      return matchesSearch;
    });

    // 显示数据
    if (this.currentViewMode === 'table') {
      this.displayTableView(this.filteredPods);
    } else {
      this.displayCardView(this.filteredPods);
    }

    // 更新选择状态
    this.updateBatchActions();
  }

  // 表格视图显示
  displayTableView(pods) {
    const tbody = document.getElementById('pods-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (pods.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center py-4">
            <i class="fas fa-cube fa-3x text-muted mb-3"></i>
            <h5 class="text-muted">暂无Pod</h5>
            <p class="text-muted">当前筛选条件下没有找到Pod</p>
          </td>
        </tr>
      `;
      return;
    }

    pods.forEach(pod => {
      const row = this.createTableRow(pod);
      tbody.appendChild(row);
    });
  }

  // 创建表格行
  createTableRow(pod) {
    const row = document.createElement('tr');
    row.dataset.podName = pod.name;
    row.dataset.podNamespace = pod.namespace;
    
    const isSelected = this.selectedPods.has(`${pod.namespace}/${pod.name}`);
    if (isSelected) {
      row.classList.add('selected');
    }

    const statusClass = this.getStatusClass(pod.status);
    const createdTime = pod.created_at ? new Date(pod.created_at) : null;
    const timeAgo = createdTime ? this.formatTimeAgo(createdTime) : '-';

    row.innerHTML = `
      <td>
        <input type="checkbox" class="pod-checkbox" 
               ${isSelected ? 'checked' : ''} 
               data-pod-id="${pod.namespace}/${pod.name}">
      </td>
      <td>
        <span class="status-badge ${statusClass}">
          ${this.getStatusText(pod.status)}
        </span>
      </td>
      <td>
        <div class="pod-name-cell">
          <strong>${pod.name}</strong>
          ${pod.labels && pod.labels.app ? 
            `<small class="text-muted d-block">app: ${pod.labels.app}</small>` : ''}
        </div>
      </td>
      <td>${pod.namespace}</td>
      <td>
        ${pod.node_name ? 
          `<span class="node-badge">${pod.node_name}</span>` : 
          '<span class="text-muted">-</span>'}
      </td>
      <td>
        <div class="resource-info">
          <small>CPU: ${pod.cpu || '0m'}</small><br>
          <small>内存: ${pod.memory || '0Mi'}</small>
        </div>
      </td>
      <td>
        <span class="restart-count ${pod.restart_count > 0 ? 'text-warning' : ''}">
          ${pod.restart_count || 0}
        </span>
      </td>
      <td>
        <small title="${pod.created_at || ''}" class="time-ago">
          ${timeAgo}
        </small>
      </td>
      <td>
        <div class="action-buttons">
          <button class="btn btn-outline-primary btn-sm" 
                  onclick="podManager.showPodDetail('${pod.namespace}', '${pod.name}')"
                  title="查看详情">
            <i class="fas fa-eye"></i>
          </button>
          <button class="btn btn-outline-info btn-sm" 
                  onclick="podManager.showPodLogs('${pod.namespace}', '${pod.name}')"
                  title="查看日志">
            <i class="fas fa-file-alt"></i>
          </button>
          <button class="btn btn-outline-success btn-sm" 
                  onclick="podManager.showPodYaml('${pod.namespace}', '${pod.name}')"
                  title="查看YAML">
            <i class="fas fa-code"></i>
          </button>
          <button class="btn btn-outline-warning btn-sm" 
                  onclick="podManager.showPodTerminal('${pod.namespace}', '${pod.name}')"
                  title="终端">
            <i class="fas fa-terminal"></i>
          </button>
          <button class="btn btn-outline-danger btn-sm" 
                  onclick="podManager.deletePod('${pod.namespace}', '${pod.name}')"
                  title="删除">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </td>
    `;

    return row;
  }

  // 卡片视图显示
  displayCardView(pods) {
    const container = document.getElementById('pods-cards-container');
    if (!container) return;

    container.innerHTML = '';

    if (pods.length === 0) {
      container.innerHTML = `
        <div class="col-12">
          <div class="empty-state">
            <i class="fas fa-cube fa-3x text-muted"></i>
            <h5>暂无Pod</h5>
            <p>当前筛选条件下没有找到Pod</p>
          </div>
        </div>
      `;
      return;
    }

    pods.forEach(pod => {
      const card = this.createPodCard(pod);
      container.appendChild(card);
    });
  }

  // 创建Pod卡片
  createPodCard(pod) {
    const card = document.createElement('div');
    card.className = 'pod-card';
    card.dataset.podName = pod.name;
    card.dataset.podNamespace = pod.namespace;
    
    const isSelected = this.selectedPods.has(`${pod.namespace}/${pod.name}`);
    if (isSelected) {
      card.classList.add('selected');
    }

    const statusClass = this.getStatusClass(pod.status);
    const createdTime = pod.created_at ? new Date(pod.created_at) : null;
    const timeAgo = createdTime ? this.formatTimeAgo(createdTime) : '-';

    card.innerHTML = `
      <div class="card-header d-flex justify-content-between align-items-center">
        <div class="pod-info">
          <h6 class="mb-1">${pod.name}</h6>
          <small class="text-muted">${pod.namespace}</small>
        </div>
        <div class="card-actions">
          <input type="checkbox" class="pod-checkbox me-2" 
                 ${isSelected ? 'checked' : ''} 
                 data-pod-id="${pod.namespace}/${pod.name}">
          <span class="status-badge ${statusClass}">
            ${this.getStatusText(pod.status)}
          </span>
        </div>
      </div>
      
      <div class="card-body">
        <div class="pod-details">
          <div class="detail-item mb-2">
            <small class="text-muted">节点:</small>
            <span>${pod.node_name || '-'}</span>
          </div>
          <div class="detail-item mb-2">
            <small class="text-muted">重启:</small>
            <span class="${pod.restart_count > 0 ? 'text-warning' : ''}">
              ${pod.restart_count || 0} 次
            </span>
          </div>
          <div class="detail-item mb-2">
            <small class="text-muted">创建时间:</small>
            <span class="time-ago">${timeAgo}</span>
          </div>
          ${pod.pod_ip ? `
          <div class="detail-item mb-2">
            <small class="text-muted">IP:</small>
            <span class="ip-address">${pod.pod_ip}</span>
          </div>
          ` : ''}
        </div>
        
        <div class="resource-usage mt-2">
          <small class="text-muted">资源使用:</small>
          <div class="resource-bars">
            <div class="resource-bar">
              <span>CPU: ${pod.cpu || '0m'}</span>
            </div>
            <div class="resource-bar">
              <span>内存: ${pod.memory || '0Mi'}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="card-footer">
        <div class="action-buttons w-100">
          <div class="d-flex gap-1 mb-2">
            <button class="btn btn-outline-primary btn-sm flex-fill" 
                    onclick="podManager.showPodDetail('${pod.namespace}', '${pod.name}')">
              <i class="fas fa-eye"></i> 详情
            </button>
            <button class="btn btn-outline-info btn-sm flex-fill" 
                    onclick="podManager.showPodLogs('${pod.namespace}', '${pod.name}')">
              <i class="fas fa-file-alt"></i> 日志
            </button>
          </div>
          <div class="d-flex gap-1 mb-1">
            <button class="btn btn-outline-success btn-sm flex-fill" 
                    onclick="podManager.showPodYaml('${pod.namespace}', '${pod.name}')">
              <i class="fas fa-code"></i> YAML
            </button>
            <button class="btn btn-outline-warning btn-sm flex-fill" 
                    onclick="podManager.showPodTerminal('${pod.namespace}', '${pod.name}')">
              <i class="fas fa-terminal"></i> 终端
            </button>
          </div>
          <div class="d-flex gap-1">
            <button class="btn btn-outline-danger btn-sm flex-fill" 
                    onclick="podManager.deletePod('${pod.namespace}', '${pod.name}')">
              <i class="fas fa-trash"></i> 删除
            </button>
          </div>
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (!e.target.matches('.pod-checkbox, button, .btn, .btn *')) {
        this.showPodDetail(pod.namespace, pod.name);
      }
    });

    return card;
  }

  // 更新统计信息
  updateStatistics() {
    const stats = {
      running: 0,
      pending: 0,
      failed: 0,
      total: this.pods.length
    };

    this.pods.forEach(pod => {
      switch (pod.status?.toLowerCase()) {
        case 'running':
          stats.running++;
          break;
        case 'pending':
          stats.pending++;
          break;
        case 'failed':
          stats.failed++;
          break;
      }
    });

    // 动画更新统计数字
    this.animateNumber('running-pods-count', stats.running);
    this.animateNumber('pending-pods-count', stats.pending);
    this.animateNumber('failed-pods-count', stats.failed);
    this.animateNumber('total-pods-count', stats.total);
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
    this.loadPods();
  }

  handleClusterFilter(event) {
    this.currentCluster = event.target.value;
    if (this.currentCluster) {
      this.loadNamespaces(this.currentCluster);
      this.loadPods();
    } else {
      this.showEmptyState();
    }
  }

  handleNamespaceFilter(event) {
    this.currentNamespace = event.target.value;
    this.currentPage = 1;
    this.loadPods();
  }

  handleStatusFilter(event) {
    this.currentStatus = event.target.value;
    this.currentPage = 1;
    this.loadPods();
  }

  handleViewModeChange(event) {
    this.currentViewMode = event.target.id === 'table-view' ? 'table' : 'card';
    
    const tableContent = document.getElementById('table-view-content');
    const cardContent = document.getElementById('card-view-content');
    
    if (this.currentViewMode === 'table') {
      if (tableContent) tableContent.style.display = 'block';
      if (cardContent) cardContent.style.display = 'none';
      this.displayTableView(this.filteredPods);
    } else {
      if (tableContent) tableContent.style.display = 'none';
      if (cardContent) cardContent.style.display = 'block';
      this.displayCardView(this.filteredPods);
    }
  }

  handleRefresh() {
    const refreshBtn = document.getElementById('refresh-btn');
    const icon = refreshBtn?.querySelector('i');
    
    if (icon) icon.classList.add('fa-spin');
    
    this.loadPods().finally(() => {
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
    const checkboxes = document.querySelectorAll('.pod-checkbox');
    const isChecked = event.target.checked;
    
    checkboxes.forEach(checkbox => {
      checkbox.checked = isChecked;
      const podId = checkbox.dataset.podId;
      
      if (isChecked) {
        this.selectedPods.add(podId);
      } else {
        this.selectedPods.delete(podId);
      }
    });
    
    this.updateTableRowSelection();
    this.updateBatchActions();
  }

  handleTableRowClick(event) {
    if (event.target.matches('.pod-checkbox')) {
      const podId = event.target.dataset.podId;
      const isChecked = event.target.checked;
      
      if (isChecked) {
        this.selectedPods.add(podId);
      } else {
        this.selectedPods.delete(podId);
      }
      
      this.updateTableRowSelection();
      this.updateBatchActions();
    }
  }

  // 更新表格行选择状态
  updateTableRowSelection() {
    document.querySelectorAll('.pods-table tbody tr').forEach(row => {
      const checkbox = row.querySelector('.pod-checkbox');
      if (checkbox) {
        if (checkbox.checked) {
          row.classList.add('selected');
        } else {
          row.classList.remove('selected');
        }
      }
    });
  }

  // 更新批量操作
  updateBatchActions() {
    const batchActions = document.getElementById('batch-actions');
    const selectedCount = document.getElementById('selected-count');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    
    if (selectedCount) selectedCount.textContent = this.selectedPods.size;
    
    if (batchActions) {
      if (this.selectedPods.size > 0) {
        batchActions.style.display = 'flex';
      } else {
        batchActions.style.display = 'none';
      }
    }
    
    // 更新全选复选框状态
    if (selectAllCheckbox) {
      const totalCheckboxes = document.querySelectorAll('.pod-checkbox').length;
      if (this.selectedPods.size === 0) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = false;
      } else if (this.selectedPods.size === totalCheckboxes) {
        selectAllCheckbox.indeterminate = false;
        selectAllCheckbox.checked = true;
      } else {
        selectAllCheckbox.indeterminate = true;
      }
    }
  }

  // 批量删除
  async handleBatchDelete() {
    if (this.selectedPods.size === 0) return;
    
    const result = await this.showConfirmDialog(
      '批量删除确认',
      `确定要删除选中的 ${this.selectedPods.size} 个Pod吗？此操作不可撤销。`
    );
    
    if (!result) return;
    
    this.showLoading();
    const deleteTasks = Array.from(this.selectedPods).map(podId => {
      const [namespace, name] = podId.split('/');
      return this.deletePodRequest(namespace, name);
    });
    
    try {
      const results = await Promise.allSettled(deleteTasks);
      const successful = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      
      if (failed === 0) {
        this.showNotification(`成功删除 ${successful} 个Pod`, 'success');
      } else {
        this.showNotification(`删除完成: 成功 ${successful} 个，失败 ${failed} 个`, 'warning');
      }
      
      this.selectedPods.clear();
      this.loadPods();
    } catch (error) {
      this.showNotification('批量删除失败: ' + error.message, 'error');
    } finally {
      this.hideLoading();
    }
  }


  // 显示Pod详情
  async showPodDetail(namespace, name) {
    if (!this.currentCluster || !namespace || !name) return;

    // 使用全屏模态框
    const modal = document.getElementById('pod-detail-modal');
    const titleElement = document.getElementById('pod-detail-modal-title');
    const bodyElement = document.getElementById('pod-detail-modal-body');
    
    if (titleElement) titleElement.textContent = `${namespace}/${name}`;
    if (bodyElement) {
      bodyElement.innerHTML = `
        <div class="loading-container text-center p-5">
          <div class="spinner-border text-primary" role="status"></div>
          <p class="mt-3">加载Pod详情中...</p>
        </div>
      `;
    }
    
    // 显示模态框
    if (modal) {
      const bsModal = new bootstrap.Modal(modal);
      bsModal.show();
    }
    
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/pods/${name}`);
      const data = await response.json();
      
      if (bodyElement) {
        bodyElement.innerHTML = this.generatePodDetailHTML(data.data);
        
        // 添加标签页切换事件监听
        this.setupTabSwitchHandlers(namespace, name);
      } else {
        throw new Error(data.message || '获取Pod详情失败');
      }
    } catch (error) {
      if (bodyElement) {
        bodyElement.innerHTML = `
          <div class="container-fluid">
            <div class="alert alert-danger m-4">
              <i class="fas fa-exclamation-triangle"></i>
              加载Pod详情失败: ${error.message}
            </div>
          </div>
        `;
      }
    }
  }

  // 生成Pod详情HTML - 全屏模态框版本
  generatePodDetailHTML(pod) {
    return `
      <div class="container-fluid">
        <!-- 标签页导航 -->
        <ul class="nav nav-tabs detail-tabs border-0 bg-light px-4" id="pod-detail-tabs" role="tablist">
          <li class="nav-item" role="presentation">
            <button class="nav-link active" id="overview-tab" data-bs-toggle="tab" data-bs-target="#overview" 
                    type="button" role="tab" aria-controls="overview" aria-selected="true">
              <i class="fas fa-info-circle"></i> 概览
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="monitoring-tab" data-bs-toggle="tab" data-bs-target="#monitoring" 
                    type="button" role="tab" aria-controls="monitoring" aria-selected="false">
              <i class="fas fa-chart-line"></i> 监控
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="containers-tab" data-bs-toggle="tab" data-bs-target="#containers" 
                    type="button" role="tab" aria-controls="containers" aria-selected="false">
              <i class="fas fa-cubes"></i> 容器
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="volumes-tab" data-bs-toggle="tab" data-bs-target="#volumes" 
                    type="button" role="tab" aria-controls="volumes" aria-selected="false">
              <i class="fas fa-hdd"></i> 存储卷
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button class="nav-link" id="events-tab" data-bs-toggle="tab" data-bs-target="#events" 
                    type="button" role="tab" aria-controls="events" aria-selected="false">
              <i class="fas fa-history"></i> 事件
            </button>
          </li>
        </ul>

        <!-- 标签页内容 -->
        <div class="tab-content detail-tab-content p-4" id="pod-detail-tab-content">
          <!-- 概览标签页 -->
          <div class="tab-pane fade show active" id="overview" role="tabpanel" aria-labelledby="overview-tab">
            <div class="row">
              <div class="col-md-6">
                <div class="detail-section">
                  <h6 class="section-title">
                    <i class="fas fa-info-circle"></i> 基本信息
                  </h6>
                  <div class="detail-grid">
                    <div class="detail-item">
                      <label>名称:</label>
                      <span>${pod.name}</span>
                    </div>
                    <div class="detail-item">
                      <label>命名空间:</label>
                      <span>${pod.namespace}</span>
                    </div>
                    <div class="detail-item">
                      <label>状态:</label>
                      <span class="status-badge ${this.getStatusClass(pod.status)}">
                        ${this.getStatusText(pod.status)}
                      </span>
                    </div>
                    <div class="detail-item">
                      <label>节点:</label>
                      <span>${pod.node_name || '-'}</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div class="col-md-6">
                <div class="detail-section">
                  <h6 class="section-title">
                    <i class="fas fa-network-wired"></i> 网络信息
                  </h6>
                  <div class="detail-grid">
                    <div class="detail-item">
                      <label>Pod IP:</label>
                      <span class="ip-address">${pod.pod_ip || '-'}</span>
                    </div>
                    <div class="detail-item">
                      <label>Host IP:</label>
                      <span class="ip-address">${pod.host_ip || '-'}</span>
                    </div>
                    <div class="detail-item">
                      <label>重启次数:</label>
                      <span class="restart-count ${pod.restart_count > 0 ? 'text-warning' : ''}">
                        ${pod.restart_count || 0}
                      </span>
                    </div>
                    <div class="detail-item">
                      <label>创建时间:</label>
                      <span>${pod.created_at ? this.formatTimeAgo(new Date(pod.created_at)) : '-'}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 资源使用 -->
            <div class="detail-section">
              <h6 class="section-title">
                <i class="fas fa-microchip"></i> 资源使用概况
              </h6>
              <div class="row">
                <div class="col-md-3">
                  <div class="metric-card cpu">
                    <div class="metric-label">CPU 使用量</div>
                    <div class="metric-value">${pod.cpu || '0m'}</div>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="metric-card memory">
                    <div class="metric-label">内存使用量</div>
                    <div class="metric-value">${pod.memory || '0Mi'}</div>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="metric-card">
                    <div class="metric-label">容器数量</div>
                    <div class="metric-value">${pod.containers ? pod.containers.length : 0}</div>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="metric-card">
                    <div class="metric-label">运行时长</div>
                    <div class="metric-value">${pod.created_at ? this.formatTimeAgo(new Date(pod.created_at)) : '-'}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 标签 -->
            ${pod.labels && Object.keys(pod.labels).length > 0 ? `
              <div class="detail-section">
                <h6 class="section-title">
                  <i class="fas fa-tags"></i> 标签
                </h6>
                <div class="labels-container">
                  ${Object.entries(pod.labels).map(([key, value]) => 
                    `<span class="label-badge">${key}: ${value}</span>`
                  ).join('')}
                </div>
              </div>
            ` : ''}
          </div>

          <!-- 监控标签页 -->
          <div class="tab-pane fade" id="monitoring" role="tabpanel" aria-labelledby="monitoring-tab">
            <div id="monitoring-container" class="monitoring-container">
              <!-- 监控内容将在这里加载 -->
              <div class="monitoring-placeholder text-center p-4">
                <i class="fas fa-chart-line fa-3x text-muted mb-3"></i>
                <p class="text-muted">点击刷新加载监控数据</p>
                <button class="btn btn-primary" onclick="podManager.loadMonitoringData('${pod.namespace}', '${pod.name}')">
                  <i class="fas fa-sync-alt"></i> 加载监控数据
                </button>
              </div>
            </div>
          </div>

          <!-- 容器标签页 -->
          <div class="tab-pane fade" id="containers" role="tabpanel" aria-labelledby="containers-tab">
            ${pod.containers && pod.containers.length > 0 ? `
              <div class="containers-list">
                ${pod.containers.map(container => `
                  <div class="container-item">
                    <div class="container-header">
                      <strong>${container.name}</strong>
                      <div class="container-actions">
                        <button class="btn btn-sm btn-outline-primary" 
                                onclick="podManager.showPodTerminal('${pod.namespace}', '${pod.name}', '${container.name}')"
                                title="打开终端">
                          <i class="fas fa-terminal"></i>
                        </button>
                      </div>
                    </div>
                    <div class="container-details">
                      <div class="detail-grid">
                        <div class="detail-item">
                          <label>镜像:</label>
                          <span class="container-image">${container.image}</span>
                        </div>
                        <div class="detail-item">
                          <label>状态:</label>
                          <span class="status-badge">${container.state || 'Unknown'}</span>
                        </div>
                      </div>
                      
                      ${container.resources ? `
                        <div class="resource-section mt-3">
                          <h6>资源配置</h6>
                          <div class="resource-grid">
                            ${container.resources.requests ? `
                              <div class="resource-item">
                                <label>请求:</label>
                                <span>CPU: ${container.resources.requests.cpu || '0m'}, 内存: ${container.resources.requests.memory || '0Mi'}</span>
                              </div>
                            ` : ''}
                            ${container.resources.limits ? `
                              <div class="resource-item">
                                <label>限制:</label>
                                <span>CPU: ${container.resources.limits.cpu || '0m'}, 内存: ${container.resources.limits.memory || '0Mi'}</span>
                              </div>
                            ` : ''}
                          </div>
                        </div>
                      ` : ''}
                      
                      ${container.volume_mounts && container.volume_mounts.length > 0 ? `
                        <div class="volume-mounts-section mt-3">
                          <h6>卷挂载</h6>
                          <div class="volume-mounts-list">
                            ${container.volume_mounts.map(mount => `
                              <div class="volume-mount-item">
                                <div class="mount-info">
                                  <strong>${mount.name}</strong>
                                  <span class="mount-path">${mount.mount_path}</span>
                                  ${mount.read_only ? '<span class="badge badge-secondary">只读</span>' : '<span class="badge badge-success">读写</span>'}
                                </div>
                                ${mount.sub_path ? `<div class="sub-path">子路径: ${mount.sub_path}</div>` : ''}
                              </div>
                            `).join('')}
                          </div>
                        </div>
                      ` : ''}
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : `
              <div class="no-data text-center p-4">
                <i class="fas fa-cube fa-3x text-muted mb-3"></i>
                <p class="text-muted">没有容器信息</p>
              </div>
            `}
          </div>

          <!-- 存储卷标签页 -->
          <div class="tab-pane fade" id="volumes" role="tabpanel" aria-labelledby="volumes-tab">
            ${pod.volumes && pod.volumes.length > 0 ? `
              <div class="volumes-list">
                ${pod.volumes.map(volume => `
                  <div class="volume-item card mb-3">
                    <div class="card-header d-flex justify-content-between align-items-center">
                      <h6 class="mb-0">
                        <i class="fas fa-hdd me-2"></i>
                        ${volume.name}
                      </h6>
                      <span class="badge ${this.getVolumeTypeBadgeClass(volume.type)}">${volume.type}</span>
                    </div>
                    <div class="card-body">
                      <div class="volume-details">
                        ${this.generateVolumeDetails(volume)}
                      </div>
                      
                      <!-- 显示哪些容器使用了这个卷 -->
                      ${(() => {
                        const mountedContainers = pod.containers ? 
                          pod.containers.filter(container => 
                            container.volume_mounts && 
                            container.volume_mounts.some(mount => mount.name === volume.name)
                          ) : [];
                        
                        if (mountedContainers.length > 0) {
                          return `
                            <div class="mounted-containers mt-3">
                              <h6>挂载到的容器:</h6>
                              <div class="container-list">
                                ${mountedContainers.map(container => {
                                  const relevantMounts = container.volume_mounts.filter(mount => mount.name === volume.name);
                                  return `
                                    <div class="container-mount-info">
                                      <strong>${container.name}:</strong>
                                      ${relevantMounts.map(mount => `
                                        <div class="mount-detail">
                                          <code>${mount.mount_path}</code>
                                          ${mount.read_only ? '<span class="badge badge-secondary ms-1">只读</span>' : '<span class="badge badge-success ms-1">读写</span>'}
                                          ${mount.sub_path ? `<div class="sub-path-info"><small>子路径: ${mount.sub_path}</small></div>` : ''}
                                        </div>
                                      `).join('')}
                                    </div>
                                  `;
                                }).join('')}
                              </div>
                            </div>
                          `;
                        }
                        return '<div class="text-muted mt-3"><em>此卷未被任何容器挂载</em></div>';
                      })()}
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : `
              <div class="no-data text-center p-4">
                <i class="fas fa-hdd fa-3x text-muted mb-3"></i>
                <p class="text-muted">此Pod没有配置存储卷</p>
              </div>
            `}
          </div>

          <!-- 事件标签页 -->
          <div class="tab-pane fade" id="events" role="tabpanel" aria-labelledby="events-tab">
            ${pod.events && pod.events.length > 0 ? `
              <div class="events-list">
                ${pod.events.map(event => `
                  <div class="event-item">
                    <div class="event-header">
                      <span class="event-type event-${event.type?.toLowerCase() || 'normal'}">
                        ${event.reason || 'Unknown'}
                      </span>
                      <small class="text-muted">
                        ${event.timestamp ? this.formatTimeAgo(new Date(event.timestamp)) : ''}
                      </small>
                    </div>
                    <div class="event-message">${event.message || ''}</div>
                    <div class="event-details">
                      <small class="text-muted">
                        来源: ${event.source || 'Unknown'} | 
                        计数: ${event.count || 1}
                      </small>
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : `
              <div class="no-data text-center p-4">
                <i class="fas fa-history fa-3x text-muted mb-3"></i>
                <p class="text-muted">没有事件记录</p>
              </div>
            `}
          </div>

          </div>
        </div>
      </div>
    `;
  }

  // 加载监控数据
  async loadMonitoringData(namespace, name) {
    console.log('🚀 开始加载监控数据:', namespace, name);
    
    if (!this.currentCluster || !namespace || !name) {
      console.error('❌ 参数无效:', { cluster: this.currentCluster, namespace, name });
      this.showNotification('参数无效', 'error');
      return;
    }

    const container = document.getElementById('monitoring-container');
    if (!container) {
      console.error('❌ 监控容器元素未找到');
      return;
    }

    try {
      // 检查全局监控组件是否存在
      if (typeof window.showPodMonitoring === 'function') {
        console.log('✅ 使用全局 showPodMonitoring 函数');
        window.showPodMonitoring(this.currentCluster, namespace, name, 'monitoring-container');
      } else if (window.podMonitoring && typeof window.podMonitoring.showMonitoring === 'function') {
        console.log('✅ 使用全局 podMonitoring 对象');
        await window.podMonitoring.showMonitoring(this.currentCluster, namespace, name, 'monitoring-container');
      } else {
        console.warn('⚠️ 监控组件未找到，尝试直接调用');
        
        // 等待监控组件初始化
        let retryCount = 0;
        const maxRetries = 5;
        
        while (retryCount < maxRetries && (!window.podMonitoring || typeof window.podMonitoring.showMonitoring !== 'function')) {
          console.log(`⏳ 等待监控组件初始化... (${retryCount + 1}/${maxRetries})`);
          await new Promise(resolve => setTimeout(resolve, 500));
          retryCount++;
        }
        
        if (window.podMonitoring && typeof window.podMonitoring.showMonitoring === 'function') {
          console.log('✅ 监控组件初始化完成，开始显示监控');
          await window.podMonitoring.showMonitoring(this.currentCluster, namespace, name, 'monitoring-container');
        } else {
          throw new Error('监控组件加载超时或初始化失败');
        }
      }
    } catch (error) {
      console.error('❌ 加载监控数据失败:', error);
      this.showNotification('加载监控数据失败: ' + error.message, 'error');
      
      // 显示错误状态
      container.innerHTML = `
        <div class="monitoring-error text-center p-4">
          <i class="fas fa-exclamation-triangle fa-3x text-danger mb-3"></i>
          <h5 class="text-danger">监控数据加载失败</h5>
          <p class="text-muted">${error.message}</p>
          <div class="mt-3">
            <button class="btn btn-outline-primary me-2" onclick="podManager.loadMonitoringData('${namespace}', '${name}')">
              <i class="fas fa-redo"></i> 重试
            </button>
            <small class="text-muted d-block mt-2">
              <i class="fas fa-info-circle"></i>
              监控功能需要Chart.js库支持
            </small>
          </div>
        </div>
      `;
    }
  }

  // 设置标签页切换事件处理器
  setupTabSwitchHandlers(namespace, name) {
    console.log('🎯 设置Pod详情标签页事件监听器');
    
    // 监控标签页点击事件
    const monitoringTab = document.getElementById('monitoring-tab');
    if (monitoringTab) {
      // 移除之前的事件监听器（避免重复绑定）
      if (this.handleMonitoringTabShow) {
        monitoringTab.removeEventListener('shown.bs.tab', this.handleMonitoringTabShow);
      }
      
      // 添加新的事件监听器
      const handleMonitoringTab = (event) => {
        console.log('📊 监控标签页被激活，开始加载监控数据');
        this.loadMonitoringData(namespace, name);
      };
      
      // 使用Bootstrap的标签页事件
      monitoringTab.addEventListener('shown.bs.tab', handleMonitoringTab);
      
      // 保存引用以便后续清理
      this.handleMonitoringTabShow = handleMonitoringTab;
      
      console.log('✅ 监控标签页事件监听器已设置');
    } else {
      console.warn('⚠️ 监控标签页元素未找到');
    }
    
    // 如果当前就在监控标签页，立即加载数据  
    if (monitoringTab && monitoringTab.classList.contains('active')) {
      console.log('📊 监控标签页当前已激活，立即加载监控数据');
      setTimeout(() => {
        this.loadMonitoringData(namespace, name);
      }, 100);
    }
  }

  // 关闭详情面板
  closeDetailPanel() {
    const panel = document.getElementById('pod-detail-panel');
    if (panel) {
      panel.classList.remove('open');
      
      // 停止监控组件
      if (window.podMonitoring) {
        window.podMonitoring.hide();
      }
    }
  }

  // 键盘快捷键处理
  handleKeyboardShortcuts(event) {
    // ESC 键关闭详情面板
    if (event.key === 'Escape') {
      this.closeDetailPanel();
    }
    
    // Ctrl/Cmd + F 聚焦搜索框
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
      event.preventDefault();
      const searchInput = document.getElementById('pod-search');
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
    this.totalPages = totalPages;
    
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
        <a class="page-link" href="#" onclick="podManager.goToPage(${current - 1})">上一页</a>
      </li>
    `;
    
    // 页码
    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= current - 2 && i <= current + 2)) {
        html += `
          <li class="page-item ${i === current ? 'active' : ''}">
            <a class="page-link" href="#" onclick="podManager.goToPage(${i})">${i}</a>
          </li>
        `;
      } else if (i === current - 3 || i === current + 3) {
        html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
      }
    }
    
    // 下一页
    html += `
      <li class="page-item ${current === totalPages ? 'disabled' : ''}">
        <a class="page-link" href="#" onclick="podManager.goToPage(${current + 1})">下一页</a>
      </li>
    `;
    
    return html;
  }

  goToPage(page) {
    if (page >= 1 && page <= this.totalPages) {
      this.currentPage = page;
      this.loadPods();
    }
  }

  // API 请求方法
  async deletePodRequest(namespace, name) {
    const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/pods/${name}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorData = await response.json();
        errorMsg = errorData.error || errorData.message || errorMsg;
      } catch (e) {
        // 忽略JSON解析错误，使用HTTP状态信息
      }
      throw new Error(errorMsg);
    }
    
    const data = await response.json();
    if (!data.success) {
      throw new Error(data.error || data.message || '删除操作失败');
    }
    return data;
  }


  // 删除Pod
  async deletePod(namespace, name) {
    const result = await this.showEnhancedConfirmDialog(
      '删除Pod确认',
      `确定要删除Pod "${name}" 吗？`,
      '此操作不可撤销，Pod中的所有容器将被停止并删除。',
      'danger'
    );
    
    if (!result) {
      return;
    }

    // 显示加载状态
    this.showDeletionProgress(namespace, name);

    try {
      await this.deletePodRequest(namespace, name);
      this.showNotification(`Pod "${name}" 删除成功`, 'success');
      this.loadPods();
    } catch (error) {
      console.error('Pod删除失败:', error);
      const errorMessage = error.message || '未知错误';
      this.showNotification(`删除Pod失败: ${errorMessage}`, 'error');
    }
  }


  // 显示Pod日志
  showPodLogs(namespace, podName) {
    if (!this.currentCluster) {
      this.showNotification('请先选择集群', 'error');
      return;
    }

    // 使用全局日志查看器
    if (typeof showPodLogs === 'function') {
      showPodLogs(this.currentCluster, namespace, podName);
    } else if (window.podLogsViewer) {
      window.podLogsViewer.showLogs(this.currentCluster, namespace, podName);
    } else {
      this.showNotification('日志查看器组件未加载', 'error');
    }
  }

  // 显示Pod终端
  showPodTerminal(namespace, podName) {
    if (!this.currentCluster) {
      this.showNotification('请先选择集群', 'error');
      return;
    }

    console.log('🖥️ 打开Pod终端:', namespace, podName);

    // 使用全局终端管理器
    if (typeof showPodTerminal === 'function') {
      showPodTerminal(this.currentCluster, namespace, podName);
    } else if (window.podTerminal) {
      window.podTerminal.showTerminal(this.currentCluster, namespace, podName);
    } else {
      this.showNotification('终端组件未加载', 'error');
    }
  }

  // 显示Pod YAML
  async showPodYaml(namespace, name) {
    console.log('🚀 showPodYaml called:', namespace, name);
    if (!this.currentCluster || !namespace || !name) {
      this.showNotification('缺少必要参数', 'error');
      return;
    }

    const modal = document.getElementById('pod-yaml-modal');
    const titleElement = document.getElementById('yaml-modal-title');
    const contentElement = document.getElementById('yaml-content');
    const codeElement = contentElement?.querySelector('code');
    const loadingElement = document.getElementById('yaml-loading');
    
    console.log('🔍 Modal elements found:', {
      modal: !!modal,
      titleElement: !!titleElement,
      contentElement: !!contentElement,
      codeElement: !!codeElement,
      loadingElement: !!loadingElement
    });
    
    // 更新标题
    if (titleElement) {
      titleElement.textContent = `${namespace}/${name} - YAML配置`;
    }
    
    // 显示加载状态
    if (loadingElement) {
      loadingElement.classList.remove('hidden');
      loadingElement.style.display = 'block';
    }
    if (contentElement) contentElement.style.display = 'none';
    
    // 显示模态框
    if (window.bootstrap && bootstrap.Modal) {
      const bootstrapModal = new bootstrap.Modal(modal);
      bootstrapModal.show();
    } else if (window.$ && $.fn.modal) {
      // 降级到jQuery Bootstrap
      $(modal).modal('show');
    } else {
      // 手动显示模态框
      modal.style.display = 'block';
      modal.classList.add('show');
      document.body.classList.add('modal-open');
    }
    
    // 存储当前YAML数据用于复制和下载
    this.currentYamlData = null;
    this.currentPodInfo = { namespace, name };
    
    try {
      const url = `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/pods/${name}/yaml`;
      console.log('🌐 Fetching YAML from:', url);
      const response = await fetch(url);
      console.log('📡 API Response status:', response.status);
      const data = await response.json();
      console.log('📄 API Response data:', data);
      
      if (data.success && data.data) {
        this.currentYamlData = data.data;
        
        // 应用语法高亮并显示YAML
        if (codeElement) {
          codeElement.textContent = data.data;
          this.highlightYaml(codeElement);
        }
        
        if (contentElement) contentElement.style.display = 'block';
      } else {
        throw new Error(data.error || '获取YAML配置失败');
      }
    } catch (error) {
      console.error('Failed to fetch YAML:', error);
      if (codeElement) {
        codeElement.textContent = `# 错误: ${error.message}\n# 无法获取Pod的YAML配置`;
        codeElement.className = 'yaml-error';
      }
      if (contentElement) contentElement.style.display = 'block';
    } finally {
      if (loadingElement) {
        loadingElement.classList.add('hidden');
        loadingElement.style.display = 'none';
      }
    }
  }

  // 简单的YAML语法高亮
  highlightYaml(element) {
    if (!element) return;
    
    const yaml = element.textContent;
    const lines = yaml.split('\n');
    const highlightedLines = lines.map(line => this.highlightYamlLine(line));
    
    element.innerHTML = highlightedLines.join('\n');
    element.className = 'language-yaml yaml-simple-highlight';
  }

  highlightYamlLine(line) {
    // 注释
    if (line.trim().startsWith('#')) {
      return `<span class="yaml-comment">${this.escapeHtml(line)}</span>`;
    }
    
    // 键值对
    const keyValueMatch = line.match(/^(\s*)([\w\-_]+)(\s*:\s*)(.*?)(\s*)$/);
    if (keyValueMatch) {
      const [, indent, key, separator, value, trailing] = keyValueMatch;
      let highlightedValue = value;
      
      // 数字
      if (/^\d+(\.\d+)?$/.test(value.trim())) {
        highlightedValue = `<span class="yaml-number">${this.escapeHtml(value)}</span>`;
      }
      // 布尔值
      else if (/^(true|false)$/i.test(value.trim())) {
        highlightedValue = `<span class="yaml-boolean">${this.escapeHtml(value)}</span>`;
      }
      // null
      else if (/^(null|~)$/i.test(value.trim())) {
        highlightedValue = `<span class="yaml-null">${this.escapeHtml(value)}</span>`;
      }
      // 字符串
      else if (value.trim()) {
        highlightedValue = `<span class="yaml-string">${this.escapeHtml(value)}</span>`;
      }
      
      return `${this.escapeHtml(indent)}<span class="yaml-key">${this.escapeHtml(key)}</span>${this.escapeHtml(separator)}${highlightedValue}${this.escapeHtml(trailing)}`;
    }
    
    // 默认返回原行
    return this.escapeHtml(line);
  }

  // HTML转义函数
  escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
  }

  // 复制YAML到剪贴板
  async copyYamlToClipboard() {
    if (!this.currentYamlData) {
      this.showNotification('没有可复制的YAML内容', 'warning');
      return;
    }

    try {
      await navigator.clipboard.writeText(this.currentYamlData);
      this.showCopySuccess();
      this.showNotification('YAML已复制到剪贴板', 'success');
    } catch (error) {
      // 降级方案
      const textArea = document.createElement('textarea');
      textArea.value = this.currentYamlData;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      
      this.showCopySuccess();
      this.showNotification('YAML已复制到剪贴板', 'success');
    }
  }

  // 显示复制成功提示
  showCopySuccess() {
    const modal = document.getElementById('pod-yaml-modal');
    const yamlContainer = modal?.querySelector('.yaml-container');
    
    if (yamlContainer) {
      const successTip = document.createElement('div');
      successTip.className = 'copy-success';
      successTip.innerHTML = '<i class="fas fa-check"></i> 已复制';
      yamlContainer.appendChild(successTip);
      
      setTimeout(() => {
        if (successTip.parentNode) {
          successTip.remove();
        }
      }, 2000);
    }
  }

  // 下载YAML文件
  downloadYaml() {
    if (!this.currentYamlData || !this.currentPodInfo) {
      this.showNotification('没有可下载的YAML内容', 'warning');
      return;
    }

    const { namespace, name } = this.currentPodInfo;
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:.]/g, '-');
    const filename = `${namespace}_${name}_${timestamp}.yaml`;
    
    const blob = new Blob([this.currentYamlData], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    this.showNotification('YAML文件下载成功', 'success');
  }

  // 工具函数
  getStatusClass(status) {
    switch (status?.toLowerCase()) {
      case 'running':
        return 'status-running';
      case 'pending':
        return 'status-pending';
      case 'succeeded':
        return 'status-succeeded';
      case 'failed':
        return 'status-failed';
      default:
        return 'status-unknown';
    }
  }

  getStatusText(status) {
    const statusMap = {
      'running': '运行中',
      'pending': '待调度',
      'succeeded': '已完成',
      'failed': '失败',
      'unknown': '未知'
    };
    return statusMap[status?.toLowerCase()] || status;
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

  // 增强的确认对话框
  async showEnhancedConfirmDialog(title, message, details, type = 'warning') {
    return new Promise((resolve) => {
      // 创建模态框
      const modal = document.createElement('div');
      modal.className = 'modal fade';
      modal.innerHTML = `
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header bg-${type} text-white">
              <h5 class="modal-title">
                <i class="fas fa-${type === 'danger' ? 'exclamation-triangle' : 'question-circle'}"></i>
                ${title}
              </h5>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <p class="mb-2"><strong>${message}</strong></p>
              <p class="text-muted small mb-0">${details}</p>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
              <button type="button" class="btn btn-${type}" id="confirm-action">确认删除</button>
            </div>
          </div>
        </div>
      `;
      
      document.body.appendChild(modal);
      
      const bootstrapModal = new bootstrap.Modal(modal);
      
      // 绑定事件
      modal.querySelector('#confirm-action').addEventListener('click', () => {
        bootstrapModal.hide();
        resolve(true);
      });
      
      modal.addEventListener('hidden.bs.modal', () => {
        document.body.removeChild(modal);
        resolve(false);
      });
      
      bootstrapModal.show();
    });
  }

  // 显示删除进度
  showDeletionProgress(namespace, name) {
    const progressNotification = document.createElement('div');
    progressNotification.id = `delete-progress-${namespace}-${name}`;
    progressNotification.className = 'alert alert-info alert-dismissible position-fixed';
    progressNotification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    progressNotification.innerHTML = `
      <div class="d-flex align-items-center">
        <div class="spinner-border spinner-border-sm me-2" role="status"></div>
        <div>正在删除Pod "${name}"...</div>
      </div>
    `;
    
    document.body.appendChild(progressNotification);
    
    // 10秒后自动移除（防止卡住）
    setTimeout(() => {
      if (progressNotification.parentNode) {
        progressNotification.remove();
      }
    }, 10000);
  }

  // 初始化自动刷新
  initAutoRefresh() {
    // 使用全局自动刷新组件
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        if (this.currentCluster) {
          this.loadPods();
        }
      }, {
        defaultInterval: 30000,
        storageKey: 'autoRefreshSettings_pods'
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

  // 存储卷相关的辅助方法
  getVolumeTypeBadgeClass(type) {
    const typeMap = {
      'PersistentVolumeClaim': 'bg-primary',
      'ConfigMap': 'bg-info', 
      'Secret': 'bg-warning',
      'EmptyDir': 'bg-secondary',
      'HostPath': 'bg-danger',
      'NFS': 'bg-success',
      'DownwardAPI': 'bg-info',
      'Projected': 'bg-dark'
    };
    return typeMap[type] || 'bg-secondary';
  }

  generateVolumeDetails(volume) {
    switch (volume.type) {
      case 'PersistentVolumeClaim':
        return `
          <div class="detail-item">
            <label>PVC名称:</label>
            <span><code>${volume.claim_name}</code></span>
          </div>
        `;
      case 'ConfigMap':
        return `
          <div class="detail-item">
            <label>ConfigMap名称:</label>
            <span><code>${volume.config_map_name}</code></span>
          </div>
        `;
      case 'Secret':
        return `
          <div class="detail-item">
            <label>Secret名称:</label>
            <span><code>${volume.secret_name}</code></span>
          </div>
        `;
      case 'EmptyDir':
        return `
          <div class="detail-item">
            <label>类型:</label>
            <span>临时存储卷 (EmptyDir)</span>
          </div>
          ${volume.size_limit ? `
            <div class="detail-item">
              <label>大小限制:</label>
              <span>${volume.size_limit}</span>
            </div>
          ` : ''}
        `;
      case 'HostPath':
        return `
          <div class="detail-item">
            <label>主机路径:</label>
            <span><code>${volume.host_path}</code></span>
          </div>
          ${volume.path_type ? `
            <div class="detail-item">
              <label>路径类型:</label>
              <span>${volume.path_type}</span>
            </div>
          ` : ''}
        `;
      case 'NFS':
        return `
          <div class="detail-item">
            <label>NFS服务器:</label>
            <span>${volume.server}</span>
          </div>
          <div class="detail-item">
            <label>NFS路径:</label>
            <span><code>${volume.path}</code></span>
          </div>
        `;
      case 'DownwardAPI':
        return `
          <div class="detail-item">
            <label>类型:</label>
            <span>Downward API (Pod元数据)</span>
          </div>
        `;
      case 'Projected':
        return `
          <div class="detail-item">
            <label>类型:</label>
            <span>投射卷 (Projected Volume)</span>
          </div>
        `;
      default:
        return `
          <div class="detail-item">
            <label>类型:</label>
            <span>${volume.type || 'Unknown'}</span>
          </div>
        `;
    }
  }

}

// 初始化Pod管理器
let podManager;
document.addEventListener('DOMContentLoaded', () => {
  podManager = new PodManager();
});

// 全局函数（供HTML中的onclick使用）
if (typeof window !== 'undefined') {
  window.podManager = {
    showPodDetail: (namespace, name) => podManager?.showPodDetail(namespace, name),
    showPodLogs: (namespace, name) => podManager?.showPodLogs(namespace, name),
    showPodYaml: (namespace, name) => podManager?.showPodYaml(namespace, name),
    showPodTerminal: (namespace, name) => podManager?.showPodTerminal(namespace, name),
    deletePod: (namespace, name) => podManager?.deletePod(namespace, name),
    goToPage: (page) => podManager?.goToPage(page)
  };
}