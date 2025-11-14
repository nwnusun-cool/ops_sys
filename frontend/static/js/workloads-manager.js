// 工作负载管理页面 - KubeSphere风格 JavaScript
console.log('🚀 workloads-manager.js 加载成功');

class WorkloadsManager {
  constructor() {
    this.currentCluster = null;
    this.currentNamespace = '';
    this.currentWorkloadType = '';
    this.searchQuery = '';
    this.currentPage = 1;
    this.itemsPerPage = 20;
    this.workloads = [];
    this.filteredWorkloads = [];
    this.currentViewMode = 'card';
    this.autoRefreshInterval = null;
    this.autoRefreshEnabled = true;
    this.refreshIntervalTime = 3000; // 3秒刷新间隔
    this.lastDataHash = null;
    this.currentWorkloadDetail = null;
    this.stateManager = new K8sStateManager('workloads');
    this.operationsInProgress = new Set(); // 跟踪进行中的操作
    this.workloadStatuses = new Map(); // 缓存工作负载状态
    
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadClusters().then(() => {
      this.restorePageState();
    });
    this.showEmptyState();
    this.updateAutoRefreshButton();
    
    // 定期清理过期的操作状态 
    setInterval(() => {
      this.cleanupExpiredOperations();
    }, 30000); // 30秒清理一次
  }

  // 清理过期的操作状态
  cleanupExpiredOperations() {
    // 清理超过5分钟的操作状态
    const now = Date.now();
    for (const operationKey of this.operationsInProgress) {
      const statusTime = this.workloadStatuses.get(operationKey + '_time');
      if (statusTime && (now - statusTime > 300000)) { // 5分钟
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.workloadStatuses.delete(operationKey + '_time');
      }
    }
  }

  // 恢复页面状态
  async restorePageState() {
    const state = this.stateManager.loadState();
    
    if (state.clusterId) {
      await K8sPageHelper.restoreSelectValue('cluster-filter', state.clusterId, 
        (clusterId) => {
          this.currentCluster = clusterId;
          this.handleClusterChange(clusterId).then(() => {
            if (state.namespace) {
              K8sPageHelper.restoreSelectValue('namespace-filter', state.namespace,
                (namespace) => {
                  this.currentNamespace = namespace;
                  this.filterWorkloads();
                }
              );
            }
          });
        }
      );
    }

    if (state.filters) {
      if (state.filters.workloadType) {
        K8sPageHelper.restoreSelectValue('workload-type-filter', state.filters.workloadType,
          (type) => {
            this.currentWorkloadType = type;
            this.filterWorkloads();
          }
        );
      }
    }
  }

  bindEvents() {
    // 集群选择 - 添加状态保存
    document.getElementById('cluster-filter').addEventListener('change', (e) => {
      this.stateManager.updateStateField('clusterId', e.target.value);
      this.handleClusterChange(e.target.value);
    });

    // 过滤器 - 添加状态保存
    document.getElementById('workload-type-filter').addEventListener('change', (e) => {
      this.currentWorkloadType = e.target.value;
      const currentState = this.stateManager.loadState();
      const filters = currentState.filters || {};
      filters.workloadType = e.target.value;
      this.stateManager.updateStateField('filters', filters);
      this.filterWorkloads();
    });

    document.getElementById('namespace-filter').addEventListener('change', (e) => {
      this.currentNamespace = e.target.value;
      this.stateManager.updateStateField('namespace', e.target.value);
      this.filterWorkloads();
    });

    // 搜索
    document.getElementById('workload-search').addEventListener('input', 
      this.debounce((e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.filterWorkloads();
      }, 300)
    );

    // 视图切换
    document.querySelectorAll('input[name="view-mode"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        this.currentViewMode = e.target.id.replace('-view', '');
        this.switchView();
      });
    });

    // 刷新按钮
    document.getElementById('refresh-btn').addEventListener('click', () => {
      this.loadWorkloads();
    });

    // 自动刷新切换按钮
    document.getElementById('auto-refresh-toggle').addEventListener('click', () => {
      this.toggleAutoRefresh();
      this.updateAutoRefreshButton();
    });

    // 扩缩容模态框
    document.getElementById('confirm-scale-btn').addEventListener('click', () => {
      this.confirmScale();
    });

    // 侧滑面板关闭
    document.getElementById('close-detail-panel').addEventListener('click', () => {
      this.closeDetailPanel();
    });
  }

  // 加载集群列表
  async loadClusters() {
    try {
      const response = await fetch('/api/k8s/clusters?active_only=true');
      const result = await response.json();
      
      if (result.success) {
        const select = document.getElementById('cluster-filter');
        select.innerHTML = '<option value="">选择集群...</option>';
        
        result.data.forEach(cluster => {
          const option = document.createElement('option');
          option.value = cluster.id;
          option.textContent = `${cluster.name} (${cluster.cluster_status})`;
          select.appendChild(option);
        });
      }
    } catch (error) {
      console.error('Failed to load clusters:', error);
      this.showError('加载集群失败');
    }
  }

  // 处理集群选择变化
  async handleClusterChange(clusterId) {
    if (!clusterId) {
      this.currentCluster = null;
      this.showEmptyState();
      return;
    }

    this.currentCluster = parseInt(clusterId);
    
    // 加载命名空间
    await this.loadNamespaces();
    
    // 加载工作负载
    await this.loadWorkloads();
    
    // 启动自动刷新
    this.startAutoRefresh();
  }

  // 加载命名空间
  async loadNamespaces() {
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces`);
      const result = await response.json();
      
      if (result.success) {
        const select = document.getElementById('namespace-filter');
        select.innerHTML = '<option value="">所有命名空间</option>';
        
        result.data.forEach(ns => {
          const option = document.createElement('option');
          option.value = ns.name;
          option.textContent = ns.name;
          select.appendChild(option);
        });
      }
    } catch (error) {
      console.error('Failed to load namespaces:', error);
    }
  }

  // 加载工作负载
  async loadWorkloads() {
    if (!this.currentCluster) return;

    this.showLoadingState();

    try {
      // 根据选择的工作负载类型确定API端点
      const workloadType = this.currentWorkloadType || 'deployment';
      let endpoint = '';
      
      switch (workloadType) {
        case 'deployment':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/deployments`;
          break;
        case 'replicaset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/replicasets`;
          break;
        case 'daemonset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/daemonsets`;
          break;
        case 'statefulset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/statefulsets`;
          break;
        case 'job':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/jobs`;
          break;
        case 'cronjob':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/cronjobs`;
          break;
        default:
          endpoint = `/api/k8s/clusters/${this.currentCluster}/deployments`;
      }

      const params = new URLSearchParams({
        page: this.currentPage,
        per_page: this.itemsPerPage
      });

      if (this.currentNamespace) {
        params.append('namespace', this.currentNamespace);
      }

      const response = await fetch(`${endpoint}?${params}`);
      const result = await response.json();

      if (result.success) {
        this.workloads = result.data.map(item => ({
          ...item,
          type: workloadType
        }));
        
        this.filterWorkloads();
        this.updateStats();
      } else {
        throw new Error(result.error || '加载失败');
      }
    } catch (error) {
      console.error('Failed to load workloads:', error);
      this.showError('加载工作负载失败: ' + error.message);
      this.workloads = [];
      this.showEmptyState();
    }
  }

  // 过滤工作负载
  filterWorkloads() {
    this.filteredWorkloads = this.workloads.filter(workload => {
      // 命名空间过滤
      if (this.currentNamespace && workload.namespace !== this.currentNamespace) {
        return false;
      }

      // 搜索过滤
      if (this.searchQuery) {
        const searchFields = [workload.name, workload.namespace].join(' ').toLowerCase();
        if (!searchFields.includes(this.searchQuery)) {
          return false;
        }
      }

      return true;
    });

    this.displayWorkloads();
  }

  // 显示工作负载
  displayWorkloads() {
    if (this.filteredWorkloads.length === 0) {
      this.showEmptyState();
      return;
    }

    this.hideEmptyState();

    if (this.currentViewMode === 'card') {
      this.displayCardView();
    } else {
      this.displayListView();
    }

    this.updatePagination();
  }

  // 显示卡片视图
  displayCardView() {
    const container = document.getElementById('workloads-cards-container');
    container.innerHTML = '';

    const startIndex = (this.currentPage - 1) * this.itemsPerPage;
    const endIndex = Math.min(startIndex + this.itemsPerPage, this.filteredWorkloads.length);
    const pageWorkloads = this.filteredWorkloads.slice(startIndex, endIndex);

    pageWorkloads.forEach(workload => {
      const card = this.createWorkloadCard(workload);
      container.appendChild(card);
    });
  }

  // 创建工作负载卡片
  createWorkloadCard(workload) {
    const operationKey = `${workload.name}-${workload.namespace}-${workload.type}`;
    const isInProgress = this.operationsInProgress.has(operationKey);
    
    const card = document.createElement('div');
    card.className = `workload-card ${workload.type} ${isInProgress ? 'operation-in-progress' : ''}`;
    card.setAttribute('data-workload', workload.name);
    card.setAttribute('data-namespace', workload.namespace);
    card.setAttribute('data-type', workload.type);

    const icon = this.getWorkloadIcon(workload.type);
    const replicaInfo = this.getReplicaInfo(workload);
    const statusHtml = this.getWorkloadStatusHtml(workload);
    
    card.innerHTML = `
      <div class="workload-type-badge ${workload.type}">
        <i class="${icon}"></i> ${workload.type.toUpperCase()}
      </div>
      
      <div class="workload-card-header">
        <div>
          <div class="workload-card-title">${workload.name}</div>
          <div class="workload-namespace">${workload.namespace}</div>
        </div>
        <div class="workload-status-container">
          ${statusHtml}
        </div>
      </div>
      
      <div class="workload-card-content">
        ${replicaInfo.html}
        
        <div class="workload-metrics">
          <div class="metric-item">
            <i class="fas fa-clock"></i>
            <span>创建: ${workload.age || '未知'}</span>
          </div>
          <div class="metric-item">
            <i class="fas fa-tag"></i>
            <span>标签: ${Object.keys(workload.labels || {}).length}</span>
          </div>
        </div>
      </div>
      
      <div class="workload-card-footer">
        <div class="workload-age">
          <i class="fas fa-clock"></i>
          <span>${workload.age || '未知'}</span>
        </div>
        <div class="workload-actions">
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.showWorkloadDetail('${workload.name}', '${workload.namespace}', '${workload.type}')" title="查看详情" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-info-circle"></i>
          </button>
          <button class="action-btn action-edit" onclick="event.stopPropagation(); workloadsManager.editWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="编辑" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-edit"></i>
          </button>
          <button class="action-btn action-yaml" onclick="event.stopPropagation(); workloadsManager.editWorkloadYaml('${workload.name}', '${workload.namespace}', '${workload.type}')" title="编辑YAML" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-file-code"></i>
          </button>
          <button class="action-btn action-recreate" onclick="event.stopPropagation(); workloadsManager.recreateWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重新创建" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-sync"></i>
          </button>
          <button class="action-btn action-delete" onclick="event.stopPropagation(); workloadsManager.deleteWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="删除" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-trash"></i>
          </button>
          ${workload.type === 'deployment' ? `
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.showScaleModal('${workload.name}', '${workload.namespace}', '${workload.type}')" title="扩缩容" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-expand-arrows-alt"></i>
          </button>
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.restartWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重启" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-redo"></i>
          </button>
          ` : ''}
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (!e.target.closest('.action-btn') && !isInProgress) {
        this.showWorkloadDetail(workload.name, workload.namespace, workload.type);
      }
    });

    return card;
  }

  // 显示列表视图
  displayListView() {
    const tbody = document.getElementById('workloads-table-body');
    tbody.innerHTML = '';

    const startIndex = (this.currentPage - 1) * this.itemsPerPage;
    const endIndex = Math.min(startIndex + this.itemsPerPage, this.filteredWorkloads.length);
    const pageWorkloads = this.filteredWorkloads.slice(startIndex, endIndex);

    pageWorkloads.forEach(workload => {
      const row = this.createWorkloadRow(workload);
      tbody.appendChild(row);
    });
  }

  // 创建工作负载表格行
  createWorkloadRow(workload) {
    const operationKey = `${workload.name}-${workload.namespace}-${workload.type}`;
    const isInProgress = this.operationsInProgress.has(operationKey);
    
    const row = document.createElement('tr');
    row.className = isInProgress ? 'operation-in-progress' : '';
    row.setAttribute('data-workload', workload.name);
    row.setAttribute('data-namespace', workload.namespace);
    row.setAttribute('data-type', workload.type);

    const icon = this.getWorkloadIcon(workload.type);
    const replicaInfo = this.getReplicaInfo(workload);
    const statusHtml = this.getWorkloadStatusHtml(workload);

    row.innerHTML = `
      <td>
        <span class="workload-type-badge ${workload.type}">
          <i class="${icon}"></i> ${workload.type.toUpperCase()}
        </span>
      </td>
      <td>${workload.name}</td>
      <td>${workload.namespace}</td>
      <td>${statusHtml}</td>
      <td>${replicaInfo.text}</td>
      <td>${workload.age || '未知'}</td>
      <td>
        <div class="workload-actions">
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.showWorkloadDetail('${workload.name}', '${workload.namespace}', '${workload.type}')" title="查看详情" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-info-circle"></i>
          </button>
          <button class="action-btn action-edit" onclick="event.stopPropagation(); workloadsManager.editWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="编辑" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-edit"></i>
          </button>
          <button class="action-btn action-yaml" onclick="event.stopPropagation(); workloadsManager.editWorkloadYaml('${workload.name}', '${workload.namespace}', '${workload.type}')" title="编辑YAML" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-file-code"></i>
          </button>
          <button class="action-btn action-recreate" onclick="event.stopPropagation(); workloadsManager.recreateWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重新创建" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-sync"></i>
          </button>
          <button class="action-btn action-delete" onclick="event.stopPropagation(); workloadsManager.deleteWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="删除" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-trash"></i>
          </button>
          ${workload.type === 'deployment' ? `
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.showScaleModal('${workload.name}', '${workload.namespace}', '${workload.type}')" title="扩缩容" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-expand-arrows-alt"></i>
          </button>
          <button class="action-btn" onclick="event.stopPropagation(); workloadsManager.restartWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重启" ${isInProgress ? 'disabled' : ''}>
            <i class="fas fa-redo"></i>
          </button>
          ` : ''}
        </div>
      </td>
    `;

    row.addEventListener('click', (e) => {
      if (!e.target.closest('.action-btn') && !isInProgress) {
        this.showWorkloadDetail(workload.name, workload.namespace, workload.type);
      }
    });

    return row;
  }

  // 获取工作负载图标
  getWorkloadIcon(type) {
    const icons = {
      'deployment': 'fas fa-rocket',
      'replicaset': 'fas fa-clone',
      'daemonset': 'fas fa-layer-group',
      'statefulset': 'fas fa-database',
      'job': 'fas fa-play',
      'cronjob': 'fas fa-clock'
    };
    return icons[type] || 'fas fa-cube';
  }

  // 获取副本信息
  getReplicaInfo(workload) {
    if (workload.type === 'deployment' && workload.replicas !== undefined) {
      const ready = workload.ready_replicas || 0;
      const total = workload.replicas || 0;
      const percentage = total > 0 ? Math.round((ready / total) * 100) : 0;
      
      return {
        text: `${ready}/${total}`,
        html: `
          <div class="replica-status-enhanced">
            <span class="replica-count ${percentage === 100 ? 'healthy' : (percentage > 0 ? 'warning' : 'error')}">
              ${ready}/${total}
            </span>
            <div class="replica-progress">
              <div class="replica-progress-bar ${percentage === 100 ? '' : (percentage > 0 ? 'warning' : 'danger')}" 
                   style="width: ${percentage}%"></div>
            </div>
          </div>
        `
      };
    }
    
    return { text: '-', html: '' };
  }

  // 生成工作负载状态显示
  getWorkloadStatusHtml(workload) {
    const operationKey = `${workload.name}-${workload.namespace}-${workload.type}`;
    const isInProgress = this.operationsInProgress.has(operationKey);
    
    let status = 'unknown';
    let statusText = 'Unknown';
    
    if (isInProgress) {
      // 检查具体的操作类型
      const operationType = this.workloadStatuses.get(operationKey);
      if (operationType === 'restart') {
        status = 'restarting';
        statusText = '重启中';
      } else if (operationType === 'recreate') {
        status = 'recreating';
        statusText = '重新创建中';
      } else if (operationType === 'update') {
        status = 'updating';
        statusText = '更新中';
      } else {
        status = 'updating';
        statusText = '处理中';
      }
    } else {
      // 根据工作负载类型和副本状态确定状态
      if (workload.type === 'deployment') {
        const ready = workload.ready_replicas || 0;
        const total = workload.replicas || 0;
        
        if (total === 0) {
          status = 'stopped';
          statusText = 'Stopped';
        } else if (ready === total) {
          status = 'running';
          statusText = 'Running';
        } else if (ready > 0) {
          status = 'pending';
          statusText = 'Pending';
        } else {
          status = 'failed';
          statusText = 'Failed';
        }
      } else if (workload.type === 'job') {
        if (workload.succeeded) {
          status = 'succeeded';
          statusText = 'Succeeded';
        } else if (workload.failed) {
          status = 'failed';
          statusText = 'Failed';
        } else {
          status = 'running';
          statusText = 'Running';
        }
      } else {
        status = 'running';
        statusText = 'Running';
      }
    }
    
    return `
      <div class="workload-status status-${status}">
        <span class="workload-status-icon ${isInProgress ? 'rotating' : ''}"></span>
        <span>${statusText}</span>
      </div>
    `;
  }

  // 切换视图
  switchView() {
    const cardView = document.getElementById('card-view-content');
    const listView = document.getElementById('list-view-content');

    if (this.currentViewMode === 'card') {
      cardView.style.display = 'block';
      listView.style.display = 'none';
    } else {
      cardView.style.display = 'none';
      listView.style.display = 'block';
    }

    this.displayWorkloads();
  }

  // 显示工作负载详情
  async showWorkloadDetail(name, namespace, type) {
    if (!this.currentCluster) return;

    try {
      let endpoint = '';
      switch (type) {
        case 'deployment':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/deployments/${name}`;
          break;
        // TODO: 添加其他工作负载类型的详情API
        default:
          this.showError('暂不支持该类型工作负载的详情查看');
          return;
      }

      const response = await fetch(endpoint);
      const result = await response.json();

      if (result.success) {
        this.currentWorkloadDetail = {
          ...result.data,
          type,
          namespace,
          name
        };
        this.displayWorkloadDetail();
        this.openDetailPanel();
      } else {
        this.showError('加载详情失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to load workload detail:', error);
      this.showError('加载详情失败');
    }
  }

  // 显示工作负载详情内容
  displayWorkloadDetail() {
    if (!this.currentWorkloadDetail) return;

    const content = document.getElementById('workload-detail-panel').querySelector('.detail-panel-content');
    const workload = this.currentWorkloadDetail;

    document.getElementById('detail-workload-name').textContent = workload.name;

    content.innerHTML = `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-info-circle"></i>
          基本信息
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <label>名称</label>
            <span>${workload.name}</span>
          </div>
          <div class="detail-item">
            <label>命名空间</label>
            <span>${workload.namespace}</span>
          </div>
          <div class="detail-item">
            <label>类型</label>
            <span>${workload.type.toUpperCase()}</span>
          </div>
          <div class="detail-item">
            <label>创建时间</label>
            <span>${workload.age || '未知'}</span>
          </div>
        </div>
      </div>

      ${workload.type === 'deployment' ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-chart-bar"></i>
          副本状态
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <label>期望副本数</label>
            <span>${workload.replicas || 0}</span>
          </div>
          <div class="detail-item">
            <label>就绪副本数</label>
            <span>${workload.ready_replicas || 0}</span>
          </div>
          <div class="detail-item">
            <label>最新副本数</label>
            <span>${workload.updated_replicas || 0}</span>
          </div>
          <div class="detail-item">
            <label>可用副本数</label>
            <span>${workload.available_replicas || 0}</span>
          </div>
        </div>
        
        <div class="mt-3">
          <button class="btn btn-sm btn-outline-primary me-2" onclick="workloadsManager.showScaleModal('${workload.name}', '${workload.namespace}', '${workload.type}')">
            <i class="fas fa-expand-arrows-alt"></i> 扩缩容
          </button>
          <button class="btn btn-sm btn-outline-warning me-2" onclick="workloadsManager.restartWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')">
            <i class="fas fa-redo"></i> 重启
          </button>
        </div>
      </div>
      ` : ''}

      ${Object.keys(workload.labels || {}).length > 0 ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-tags"></i>
          标签
        </div>
        <div class="labels-container">
          ${Object.entries(workload.labels).map(([key, value]) => 
            `<span class="label-badge">${key}=${value}</span>`
          ).join('')}
        </div>
      </div>
      ` : ''}

      ${workload.selector && Object.keys(workload.selector).length > 0 ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-bullseye"></i>
          选择器
        </div>
        <div class="labels-container">
          ${Object.entries(workload.selector).map(([key, value]) => 
            `<span class="label-badge">${key}=${value}</span>`
          ).join('')}
        </div>
      </div>
      ` : ''}
    `;
  }

  // 显示扩缩容模态框
  showScaleModal(name, namespace, type) {
    if (type !== 'deployment') {
      this.showError('仅支持Deployment的扩缩容');
      return;
    }

    this.currentWorkloadDetail = { name, namespace, type };
    
    // 获取当前副本数
    const workload = this.workloads.find(w => w.name === name && w.namespace === namespace);
    if (workload) {
      document.getElementById('current-replicas').value = workload.replicas || 0;
      document.getElementById('target-replicas').value = workload.replicas || 0;
    }

    const modal = new bootstrap.Modal(document.getElementById('scale-modal'));
    modal.show();
  }

  // 确认扩缩容
  async confirmScale() {
    if (!this.currentWorkloadDetail) return;

    const targetReplicas = parseInt(document.getElementById('target-replicas').value);
    
    if (isNaN(targetReplicas) || targetReplicas < 0) {
      this.showError('请输入有效的副本数');
      return;
    }

    try {
      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${this.currentWorkloadDetail.namespace}/deployments/${this.currentWorkloadDetail.name}/scale`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ replicas: targetReplicas })
        }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('扩缩容操作成功');
        bootstrap.Modal.getInstance(document.getElementById('scale-modal')).hide();
        this.loadWorkloads();
      } else {
        this.showError('扩缩容失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to scale workload:', error);
      this.showError('扩缩容失败');
    }
  }

  // 重启工作负载
  async restartWorkload(name, namespace, type) {
    if (type !== 'deployment') {
      this.showError('仅支持Deployment的重启');
      return;
    }

    if (!confirm(`确定要重启 ${type} "${name}" 吗？`)) {
      return;
    }

    const operationKey = `${name}-${namespace}-${type}`;
    
    try {
      // 标记操作开始
      this.operationsInProgress.add(operationKey);
      this.workloadStatuses.set(operationKey, 'restart');
      this.workloadStatuses.set(operationKey + '_time', Date.now());
      this.refreshDisplayWithoutApiCall();

      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/deployments/${name}/restart`,
        { method: 'POST' }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('重启操作已启动');
        // 延迟清除状态，让用户看到重启中的状态
        setTimeout(() => {
          this.operationsInProgress.delete(operationKey);
          this.workloadStatuses.delete(operationKey);
          this.loadWorkloads();
        }, 2000);
      } else {
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.showError('重启失败: ' + result.error);
        this.refreshDisplayWithoutApiCall();
      }
    } catch (error) {
      this.operationsInProgress.delete(operationKey);
      this.workloadStatuses.delete(operationKey);
      console.error('Failed to restart workload:', error);
      this.showError('重启失败');
      this.refreshDisplayWithoutApiCall();
    }
  }

  // 编辑工作负载 (表单形式)
  async editWorkload(name, namespace, type) {
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/${type}s/${name}`);
      const result = await response.json();

      if (result.success) {
        this.showEditModal(result.data, type);
      } else {
        this.showError('获取工作负载信息失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to get workload for edit:', error);
      this.showError('获取工作负载信息失败');
    }
  }

  // 编辑工作负载YAML
  async editWorkloadYaml(name, namespace, type) {
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/${type}s/${name}/yaml`);
      const result = await response.json();

      if (result.success) {
        this.showYamlEditor(result.data, name, namespace, type);
      } else {
        this.showError('获取YAML失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to get YAML:', error);
      this.showError('获取YAML失败');
    }
  }

  // 重新创建工作负载
  async recreateWorkload(name, namespace, type) {
    if (!confirm(`确定要重新创建 ${type} "${name}" 吗？\n此操作将删除现有工作负载并重新创建，可能导致短暂的服务中断。`)) {
      return;
    }

    const operationKey = `${name}-${namespace}-${type}`;
    
    try {
      // 标记操作开始
      this.operationsInProgress.add(operationKey);
      this.workloadStatuses.set(operationKey, 'recreate');
      this.workloadStatuses.set(operationKey + '_time', Date.now());
      this.refreshDisplayWithoutApiCall();

      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/${type}s/${name}/recreate`,
        { method: 'POST' }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('重新创建操作已启动');
        // 延迟清除状态
        setTimeout(() => {
          this.operationsInProgress.delete(operationKey);
          this.workloadStatuses.delete(operationKey);
          this.loadWorkloads();
        }, 3000); // 重新创建需要更长时间
      } else {
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.showError('重新创建失败: ' + result.error);
        this.refreshDisplayWithoutApiCall();
      }
    } catch (error) {
      this.operationsInProgress.delete(operationKey);
      this.workloadStatuses.delete(operationKey);
      console.error('Failed to recreate workload:', error);
      this.showError('重新创建失败');
      this.refreshDisplayWithoutApiCall();
    }
  }

  // 删除工作负载
  async deleteWorkload(name, namespace, type) {
    if (!confirm(`确定要删除 ${type} "${name}" 吗？\n此操作不可撤销！`)) {
      return;
    }

    const operationKey = `${name}-${namespace}-${type}`;
    
    try {
      // 标记操作开始
      this.operationsInProgress.add(operationKey);
      this.workloadStatuses.set(operationKey, 'delete');
      this.workloadStatuses.set(operationKey + '_time', Date.now());
      this.refreshDisplayWithoutApiCall();

      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/${type}s/${name}`,
        { method: 'DELETE' }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('删除操作成功');
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.loadWorkloads();
      } else {
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.showError('删除失败: ' + result.error);
        this.refreshDisplayWithoutApiCall();
      }
    } catch (error) {
      this.operationsInProgress.delete(operationKey);
      this.workloadStatuses.delete(operationKey);
      console.error('Failed to delete workload:', error);
      this.showError('删除失败');
      this.refreshDisplayWithoutApiCall();
    }
  }

  // 显示编辑模态框
  showEditModal(workloadData, type) {
    // TODO: 创建编辑表单模态框
    this.showError('编辑功能正在开发中');
  }

  // 显示YAML编辑器
  showYamlEditor(yamlContent, name, namespace, type) {
    // 创建YAML编辑器模态框
    const modalHtml = `
      <div class="modal fade" id="yaml-editor-modal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-xl">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">
                <i class="fas fa-file-code me-2"></i>编辑 ${type.toUpperCase()} - ${name}
              </h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle me-2"></i>
                请谨慎编辑YAML文件，错误的配置可能导致工作负载无法正常运行
              </div>
              <textarea id="yaml-editor" class="form-control" rows="20" style="font-family: 'Monaco', 'Consolas', monospace; font-size: 12px;">${yamlContent}</textarea>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
              <button type="button" class="btn btn-primary" onclick="workloadsManager.saveYamlChanges('${name}', '${namespace}', '${type}')">
                <i class="fas fa-save me-2"></i>保存更改
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    // 移除已存在的模态框
    const existingModal = document.getElementById('yaml-editor-modal');
    if (existingModal) {
      existingModal.remove();
    }

    // 添加新模态框
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // 显示模态框
    const modal = new bootstrap.Modal(document.getElementById('yaml-editor-modal'));
    modal.show();

    // 模态框关闭时清理
    document.getElementById('yaml-editor-modal').addEventListener('hidden.bs.modal', function () {
      this.remove();
    });
  }

  // 保存YAML更改
  async saveYamlChanges(name, namespace, type) {
    const yamlContent = document.getElementById('yaml-editor').value;

    if (!yamlContent.trim()) {
      this.showError('YAML内容不能为空');
      return;
    }

    const operationKey = `${name}-${namespace}-${type}`;
    
    try {
      // 标记操作开始
      this.operationsInProgress.add(operationKey);
      this.workloadStatuses.set(operationKey, 'update');
      this.workloadStatuses.set(operationKey + '_time', Date.now());
      this.refreshDisplayWithoutApiCall();

      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/${type}s/${name}/yaml`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ yaml: yamlContent })
        }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('YAML更新成功');
        bootstrap.Modal.getInstance(document.getElementById('yaml-editor-modal')).hide();
        
        // 延迟清除状态
        setTimeout(() => {
          this.operationsInProgress.delete(operationKey);
          this.workloadStatuses.delete(operationKey);
          this.loadWorkloads();
        }, 2000);
      } else {
        this.operationsInProgress.delete(operationKey);
        this.workloadStatuses.delete(operationKey);
        this.showError('YAML更新失败: ' + result.error);
        this.refreshDisplayWithoutApiCall();
      }
    } catch (error) {
      this.operationsInProgress.delete(operationKey);
      this.workloadStatuses.delete(operationKey);
      console.error('Failed to save YAML:', error);
      this.showError('YAML更新失败');
      this.refreshDisplayWithoutApiCall();
    }
  }

  // 刷新显示但不调用API
  refreshDisplayWithoutApiCall() {
    this.filterWorkloads();
  }

  // 启动自动刷新
  startAutoRefresh() {
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval);
    }

    this.autoRefreshInterval = setInterval(async () => {
      if (this.autoRefreshEnabled && this.currentCluster) {
        await this.refreshWorkloadsSeamlessly();
      }
    }, this.refreshIntervalTime);
  }

  // 停止自动刷新
  stopAutoRefresh() {
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval);
      this.autoRefreshInterval = null;
    }
  }

  // 切换自动刷新
  toggleAutoRefresh() {
    this.autoRefreshEnabled = !this.autoRefreshEnabled;
    
    if (this.autoRefreshEnabled) {
      this.showSuccess('自动刷新已启用');
      this.startAutoRefresh();
    } else {
      this.showSuccess('自动刷新已停用');
      this.stopAutoRefresh();
    }
  }

  // 更新自动刷新按钮状态
  updateAutoRefreshButton() {
    const button = document.getElementById('auto-refresh-toggle');
    const icon = button.querySelector('i');
    
    if (this.autoRefreshEnabled) {
      button.classList.remove('btn-outline-success');
      button.classList.add('btn-success');
      icon.className = 'fas fa-pause';
      button.title = '停止自动刷新';
    } else {
      button.classList.remove('btn-success');
      button.classList.add('btn-outline-success');
      icon.className = 'fas fa-play';
      button.title = '开始自动刷新';
    }
  }

  // 无缝刷新工作负载
  async refreshWorkloadsSeamlessly() {
    if (!this.currentCluster) return;

    try {
      // 获取当前选择的工作负载类型
      const workloadType = this.currentWorkloadType || 'deployment';
      let endpoint = '';
      
      switch (workloadType) {
        case 'deployment':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/deployments`;
          break;
        case 'replicaset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/replicasets`;
          break;
        case 'daemonset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/daemonsets`;
          break;
        case 'statefulset':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/statefulsets`;
          break;
        case 'job':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/jobs`;
          break;
        case 'cronjob':
          endpoint = `/api/k8s/clusters/${this.currentCluster}/cronjobs`;
          break;
        default:
          endpoint = `/api/k8s/clusters/${this.currentCluster}/deployments`;
      }

      const params = new URLSearchParams({
        page: this.currentPage,
        per_page: this.itemsPerPage
      });

      if (this.currentNamespace) {
        params.append('namespace', this.currentNamespace);
      }

      const response = await fetch(`${endpoint}?${params}`);
      const result = await response.json();

      if (result.success) {
        const newWorkloads = result.data.map(item => ({
          ...item,
          type: workloadType
        }));

        // 生成数据哈希值
        const newDataHash = this.generateDataHash(newWorkloads);

        // 如果数据发生变化，则更新UI
        if (this.lastDataHash !== newDataHash) {
          this.lastDataHash = newDataHash;
          
          // 平滑更新工作负载数据
          await this.updateWorkloadsSeamlessly(newWorkloads);
          
          this.updateStats();
        }
      }
    } catch (error) {
      console.error('Auto refresh failed:', error);
      // 静默处理错误，不打断用户体验
    }
  }

  // 生成数据哈希值
  generateDataHash(workloads) {
    const dataString = JSON.stringify(workloads.map(w => ({
      name: w.name,
      namespace: w.namespace,
      type: w.type,
      replicas: w.replicas,
      ready_replicas: w.ready_replicas,
      updated_replicas: w.updated_replicas,
      available_replicas: w.available_replicas
    })));
    
    // 简单哈希函数
    let hash = 0;
    for (let i = 0; i < dataString.length; i++) {
      const char = dataString.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // 转换为32位整数
    }
    return hash;
  }

  // 平滑更新工作负载
  async updateWorkloadsSeamlessly(newWorkloads) {
    const oldWorkloads = [...this.workloads];
    
    // 保留正在进行的操作状态
    const updatedWorkloads = newWorkloads.map(newWorkload => {
      const operationKey = `${newWorkload.name}-${newWorkload.namespace}-${newWorkload.type}`;
      if (this.operationsInProgress.has(operationKey)) {
        // 如果操作正在进行中，保持当前状态
        return { ...newWorkload, _operationInProgress: true };
      }
      return newWorkload;
    });
    
    this.workloads = updatedWorkloads;
    
    // 过滤和重新显示
    this.filterWorkloads();
    
    // 添加平滑过渡效果
    this.addUpdateTransitions(oldWorkloads, updatedWorkloads);
  }

  // 添加更新过渡效果
  addUpdateTransitions(oldWorkloads, newWorkloads) {
    // 创建新旧数据的映射
    const oldMap = new Map(oldWorkloads.map(w => [`${w.name}-${w.namespace}`, w]));
    const newMap = new Map(newWorkloads.map(w => [`${w.name}-${w.namespace}`, w]));
    
    // 查找变化的工作负载
    const changedWorkloads = [];
    
    newWorkloads.forEach(newWorkload => {
      const key = `${newWorkload.name}-${newWorkload.namespace}`;
      const oldWorkload = oldMap.get(key);
      
      if (oldWorkload) {
        // 检查是否有变化
        const hasChanged = JSON.stringify(this.getWorkloadState(oldWorkload)) !== 
                          JSON.stringify(this.getWorkloadState(newWorkload));
        
        if (hasChanged) {
          changedWorkloads.push({
            name: newWorkload.name,
            namespace: newWorkload.namespace,
            type: newWorkload.type
          });
        }
      }
    });
    
    // 应用闪烁效果到变化的工作负载
    changedWorkloads.forEach(workload => {
      this.highlightWorkloadUpdate(workload);
    });
  }

  // 获取工作负载状态用于比较
  getWorkloadState(workload) {
    return {
      replicas: workload.replicas,
      ready_replicas: workload.ready_replicas,
      updated_replicas: workload.updated_replicas,
      available_replicas: workload.available_replicas
    };
  }

  // 高亮显示更新的工作负载
  highlightWorkloadUpdate(workload) {
    const selector = `[data-workload="${workload.name}"][data-namespace="${workload.namespace}"]`;
    const element = document.querySelector(selector);
    
    if (element) {
      // 添加更新高亮效果
      element.classList.add('workload-updated');
      
      // 2秒后移除高亮效果
      setTimeout(() => {
        element.classList.remove('workload-updated');
      }, 2000);
    }
  }

  // 更新统计
  updateStats() {
    const stats = {
      deployment: 0,
      replicaset: 0,
      statefulset: 0,
      daemonset: 0
    };

    this.workloads.forEach(workload => {
      if (stats.hasOwnProperty(workload.type)) {
        stats[workload.type]++;
      }
    });

    document.getElementById('deploymentCount').textContent = stats.deployment;
    document.getElementById('replicasetCount').textContent = stats.replicaset;
    document.getElementById('statefulsetCount').textContent = stats.statefulset;
    document.getElementById('daemonsetCount').textContent = stats.daemonset;
  }

  // 更新分页
  updatePagination() {
    const totalPages = Math.ceil(this.filteredWorkloads.length / this.itemsPerPage);
    
    if (totalPages <= 1) {
      document.getElementById('pagination-section').style.display = 'none';
      return;
    }

    document.getElementById('pagination-section').style.display = 'flex';
    
    const startIndex = (this.currentPage - 1) * this.itemsPerPage + 1;
    const endIndex = Math.min(this.currentPage * this.itemsPerPage, this.filteredWorkloads.length);
    
    document.getElementById('items-range').textContent = `${startIndex}-${endIndex}`;
    document.getElementById('total-items').textContent = this.filteredWorkloads.length;

    // 生成分页控件
    const controls = document.getElementById('pagination-controls');
    controls.innerHTML = '';

    // 上一页
    const prevBtn = document.createElement('li');
    prevBtn.className = `page-item ${this.currentPage === 1 ? 'disabled' : ''}`;
    prevBtn.innerHTML = `
      <a class="page-link" href="#" onclick="workloadsManager.goToPage(${this.currentPage - 1})">
        <i class="fas fa-chevron-left"></i>
      </a>
    `;
    controls.appendChild(prevBtn);

    // 页码
    const startPage = Math.max(1, this.currentPage - 2);
    const endPage = Math.min(totalPages, this.currentPage + 2);

    for (let i = startPage; i <= endPage; i++) {
      const pageBtn = document.createElement('li');
      pageBtn.className = `page-item ${i === this.currentPage ? 'active' : ''}`;
      pageBtn.innerHTML = `
        <a class="page-link" href="#" onclick="workloadsManager.goToPage(${i})">${i}</a>
      `;
      controls.appendChild(pageBtn);
    }

    // 下一页
    const nextBtn = document.createElement('li');
    nextBtn.className = `page-item ${this.currentPage === totalPages ? 'disabled' : ''}`;
    nextBtn.innerHTML = `
      <a class="page-link" href="#" onclick="workloadsManager.goToPage(${this.currentPage + 1})">
        <i class="fas fa-chevron-right"></i>
      </a>
    `;
    controls.appendChild(nextBtn);
  }

  // 跳转页面
  goToPage(page) {
    const totalPages = Math.ceil(this.filteredWorkloads.length / this.itemsPerPage);
    
    if (page >= 1 && page <= totalPages) {
      this.currentPage = page;
      this.displayWorkloads();
    }
  }

  // 打开详情面板
  openDetailPanel() {
    document.getElementById('workload-detail-panel').classList.add('open');
  }

  // 关闭详情面板
  closeDetailPanel() {
    document.getElementById('workload-detail-panel').classList.remove('open');
  }

  // 显示状态管理
  showLoadingState() {
    // TODO: 实现加载状态显示
    console.log('Loading workloads...');
  }

  showEmptyState() {
    const cardContainer = document.getElementById('workloads-cards-container');
    const listContainer = document.getElementById('workloads-table-body');
    
    cardContainer.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-tasks fa-3x"></i>
        <h5>暂无工作负载</h5>
        <p>请先选择一个集群查看工作负载</p>
      </div>
    `;
    
    listContainer.innerHTML = `
      <tr>
        <td colspan="6" class="text-center py-5">
          <div class="empty-state">
            <i class="fas fa-tasks fa-3x"></i>
            <h5>暂无工作负载</h5>
            <p>请先选择一个集群查看工作负载</p>
          </div>
        </td>
      </tr>
    `;
  }

  hideEmptyState() {
    // 空状态会被新内容覆盖，不需要特别处理
  }

  // 工具函数
  debounce(func, delay) {
    let timeoutId;
    return function (...args) {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
  }

  showSuccess(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-success alert-dismissible fade show position-fixed';
    alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alert.innerHTML = `
      <i class="fas fa-check-circle me-2"></i>${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alert);
    
    setTimeout(() => {
      if (alert.parentNode) {
        alert.remove();
      }
    }, 5000);
  }

  showError(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger alert-dismissible fade show position-fixed';
    alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alert.innerHTML = `
      <i class="fas fa-exclamation-triangle me-2"></i>${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alert);
    
    setTimeout(() => {
      if (alert.parentNode) {
        alert.remove();
      }
    }, 8000);
  }
}

// 全局实例
let workloadsManager;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  workloadsManager = new WorkloadsManager();
});