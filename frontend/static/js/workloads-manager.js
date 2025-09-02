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
    this.currentWorkloadDetail = null;
    this.stateManager = new K8sStateManager('workloads');
    
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadClusters().then(() => {
      this.restorePageState();
    });
    this.showEmptyState();
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
    const card = document.createElement('div');
    card.className = `workload-card ${workload.type}`;
    card.setAttribute('data-workload', workload.name);
    card.setAttribute('data-namespace', workload.namespace);
    card.setAttribute('data-type', workload.type);

    const icon = this.getWorkloadIcon(workload.type);
    const replicaInfo = this.getReplicaInfo(workload);
    
    card.innerHTML = `
      <div class="workload-type-badge ${workload.type}">
        <i class="${icon}"></i> ${workload.type.toUpperCase()}
      </div>
      
      <div class="workload-card-header">
        <div>
          <div class="workload-card-title">${workload.name}</div>
          <div class="workload-namespace">${workload.namespace}</div>
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
          <button class="action-btn" onclick="workloadsManager.showWorkloadDetail('${workload.name}', '${workload.namespace}', '${workload.type}')" title="查看详情">
            <i class="fas fa-info-circle"></i>
          </button>
          ${workload.type === 'deployment' ? `
          <button class="action-btn" onclick="workloadsManager.showScaleModal('${workload.name}', '${workload.namespace}', '${workload.type}')" title="扩缩容">
            <i class="fas fa-expand-arrows-alt"></i>
          </button>
          <button class="action-btn" onclick="workloadsManager.restartWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重启">
            <i class="fas fa-redo"></i>
          </button>
          ` : ''}
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (!e.target.closest('.action-btn')) {
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
    const row = document.createElement('tr');
    row.setAttribute('data-workload', workload.name);
    row.setAttribute('data-namespace', workload.namespace);
    row.setAttribute('data-type', workload.type);

    const icon = this.getWorkloadIcon(workload.type);
    const replicaInfo = this.getReplicaInfo(workload);

    row.innerHTML = `
      <td>
        <span class="workload-type-badge ${workload.type}">
          <i class="${icon}"></i> ${workload.type.toUpperCase()}
        </span>
      </td>
      <td>${workload.name}</td>
      <td>${workload.namespace}</td>
      <td>${replicaInfo.text}</td>
      <td>${workload.age || '未知'}</td>
      <td>
        <div class="workload-actions">
          <button class="action-btn" onclick="workloadsManager.showWorkloadDetail('${workload.name}', '${workload.namespace}', '${workload.type}')" title="查看详情">
            <i class="fas fa-info-circle"></i>
          </button>
          ${workload.type === 'deployment' ? `
          <button class="action-btn" onclick="workloadsManager.showScaleModal('${workload.name}', '${workload.namespace}', '${workload.type}')" title="扩缩容">
            <i class="fas fa-expand-arrows-alt"></i>
          </button>
          <button class="action-btn" onclick="workloadsManager.restartWorkload('${workload.name}', '${workload.namespace}', '${workload.type}')" title="重启">
            <i class="fas fa-redo"></i>
          </button>
          ` : ''}
        </div>
      </td>
    `;

    row.addEventListener('click', (e) => {
      if (!e.target.closest('.action-btn')) {
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
          <div class="replica-status">
            <span class="replica-text">副本: ${ready}/${total}</span>
            <span class="replica-text">${percentage}%</span>
          </div>
          <div class="replica-progress">
            <div class="replica-progress-bar ${percentage === 100 ? '' : (percentage > 0 ? 'warning' : 'danger')}" 
                 style="width: ${percentage}%"></div>
          </div>
        `
      };
    }
    
    return { text: '-', html: '' };
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

    try {
      const response = await fetch(
        `/api/k8s/clusters/${this.currentCluster}/namespaces/${namespace}/deployments/${name}/restart`,
        { method: 'POST' }
      );

      const result = await response.json();

      if (result.success) {
        this.showSuccess('重启操作已启动');
        this.loadWorkloads();
      } else {
        this.showError('重启失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to restart workload:', error);
      this.showError('重启失败');
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