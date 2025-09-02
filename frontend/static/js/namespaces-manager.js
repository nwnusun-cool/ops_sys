// 命名空间管理页面 - KubeSphere风格 JavaScript
console.log('🚀 namespaces-manager.js 加载成功');

class NamespacesManager {
  constructor() {
    this.currentCluster = null;
    this.currentNamespace = '';
    this.searchQuery = '';
    this.currentPage = 1;
    this.itemsPerPage = 12;
    this.namespaces = [];
    this.filteredNamespaces = [];
    this.currentFilters = {
      status: '',
      type: ''
    };
    this.autoRefreshManager = null;
    this.currentNamespaceDetail = null;
    this.stateManager = new K8sStateManager('namespaces');
    
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadClusters().then(() => {
      this.restorePageState();
    });
    this.initAutoRefresh();
    this.showEmptyState();
  }

  // 恢复页面状态
  async restorePageState() {
    const state = this.stateManager.loadState();
    
    if (state.clusterId) {
      await K8sPageHelper.restoreSelectValue('cluster-filter', state.clusterId, 
        (clusterId) => {
          this.currentCluster = clusterId;
          this.handleClusterChange(clusterId);
        }
      );
    }

    if (state.filters) {
      if (state.filters.status) {
        K8sPageHelper.restoreSelectValue('status-filter', state.filters.status,
          (status) => {
            this.currentFilters.status = status;
          }
        );
      }
      if (state.filters.type) {
        K8sPageHelper.restoreSelectValue('type-filter', state.filters.type,
          (type) => {
            this.currentFilters.type = type;
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
    document.getElementById('status-filter').addEventListener('change', (e) => {
      this.currentFilters.status = e.target.value;
      const currentState = this.stateManager.loadState();
      const filters = currentState.filters || {};
      filters.status = e.target.value;
      this.stateManager.updateStateField('filters', filters);
      this.filterNamespaces();
    });

    document.getElementById('type-filter').addEventListener('change', (e) => {
      this.currentFilters.type = e.target.value;
      const currentState = this.stateManager.loadState();
      const filters = currentState.filters || {};
      filters.type = e.target.value;
      this.stateManager.updateStateField('filters', filters);
      this.filterNamespaces();
    });

    // 搜索
    document.getElementById('namespace-search').addEventListener('input', 
      this.debounce((e) => {
        this.searchQuery = e.target.value.toLowerCase().trim();
        this.filterNamespaces();
      }, 300)
    );

    // 刷新按钮
    document.getElementById('refresh-btn').addEventListener('click', () => {
      this.loadNamespaces();
      // 通知自动刷新管理器
      if (typeof notifyManualRefresh === 'function') {
        notifyManualRefresh();
      }
    });

    // 创建命名空间
    document.getElementById('create-namespace-btn').addEventListener('click', () => {
      this.showCreateModal();
    });

    document.getElementById('confirm-create-btn').addEventListener('click', () => {
      this.confirmCreate();
    });

    // 标签管理
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('add-label-btn') || e.target.parentElement.classList.contains('add-label-btn')) {
        this.addLabelRow();
      }
      if (e.target.classList.contains('remove-label-btn') || e.target.parentElement.classList.contains('remove-label-btn')) {
        this.removeLabelRow(e.target);
      }
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
    await this.loadNamespaces();
  }

  // 加载命名空间
  async loadNamespaces() {
    if (!this.currentCluster) return;

    this.showLoadingState();

    try {
      const params = new URLSearchParams({
        page: this.currentPage,
        per_page: this.itemsPerPage
      });

      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces?${params}`);
      const result = await response.json();

      if (result.success) {
        this.namespaces = result.data || [];
        this.filterNamespaces();
        this.updateStats();
      } else {
        throw new Error(result.error || '加载失败');
      }
    } catch (error) {
      console.error('Failed to load namespaces:', error);
      this.showError('加载命名空间失败: ' + error.message);
      this.namespaces = [];
      this.showEmptyState();
    }
  }

  // 过滤命名空间
  filterNamespaces() {
    this.filteredNamespaces = this.namespaces.filter(namespace => {
      // 搜索过滤
      if (this.searchQuery) {
        const searchFields = [namespace.name].join(' ').toLowerCase();
        if (!searchFields.includes(this.searchQuery)) {
          return false;
        }
      }

      // 状态过滤
      if (this.currentFilters.status && namespace.status !== this.currentFilters.status) {
        return false;
      }

      // 类型过滤
      if (this.currentFilters.type) {
        const isSystemNamespace = this.isSystemNamespace(namespace.name);
        if (this.currentFilters.type === 'system' && !isSystemNamespace) {
          return false;
        }
        if (this.currentFilters.type === 'user' && isSystemNamespace) {
          return false;
        }
      }

      return true;
    });

    this.displayNamespaces();
  }

  // 显示命名空间
  displayNamespaces() {
    if (this.filteredNamespaces.length === 0) {
      this.showEmptyNamespaces();
      return;
    }

    this.hideEmptyState();

    const startIndex = (this.currentPage - 1) * this.itemsPerPage;
    const endIndex = Math.min(startIndex + this.itemsPerPage, this.filteredNamespaces.length);
    const pageNamespaces = this.filteredNamespaces.slice(startIndex, endIndex);

    const container = document.getElementById('namespaces-cards-container');
    container.innerHTML = '';

    pageNamespaces.forEach(namespace => {
      const card = this.createNamespaceCard(namespace);
      container.appendChild(card);
    });

    this.updatePagination();
  }

  // 创建命名空间卡片
  createNamespaceCard(namespace) {
    const card = document.createElement('div');
    const isSystem = this.isSystemNamespace(namespace.name);
    const cardClass = isSystem ? 'system-namespace' : 'user-namespace';
    
    card.className = `namespace-card ${cardClass}`;
    card.setAttribute('data-namespace', namespace.name);

    const resourceStats = namespace.resource_stats || {};
    
    card.innerHTML = `
      <div class="namespace-card-header">
        <div>
          <div class="namespace-type-badge ${isSystem ? 'system' : 'user'}">
            <i class="fas ${isSystem ? 'fa-cogs' : 'fa-user-tag'}"></i> 
            ${isSystem ? '系统' : '用户'}
          </div>
          <div class="namespace-card-title">
            <i class="fas fa-layer-group"></i>
            ${namespace.name}
          </div>
          <span class="namespace-status-badge ${namespace.status?.toLowerCase() || 'active'}">
            ${namespace.status || 'Active'}
          </span>
        </div>
        <div class="namespace-actions">
          <button class="action-btn" onclick="namespacesManager.showNamespaceDetail('${namespace.name}')" title="查看详情">
            <i class="fas fa-info-circle"></i>
          </button>
          ${!isSystem ? `
          <button class="action-btn danger" onclick="namespacesManager.confirmDeleteNamespace('${namespace.name}')" title="删除">
            <i class="fas fa-trash"></i>
          </button>
          ` : ''}
        </div>
      </div>
      
      <div class="namespace-card-content">
        <div class="resource-stats">
          <div class="resource-stat-item">
            <i class="fas fa-cube resource-stat-icon"></i>
            <span>Pods: <span class="resource-stat-value">${resourceStats.pods || 0}</span></span>
          </div>
          <div class="resource-stat-item">
            <i class="fas fa-network-wired resource-stat-icon"></i>
            <span>Services: <span class="resource-stat-value">${resourceStats.services || 0}</span></span>
          </div>
          <div class="resource-stat-item">
            <i class="fas fa-file-alt resource-stat-icon"></i>
            <span>ConfigMaps: <span class="resource-stat-value">${resourceStats.configmaps || 0}</span></span>
          </div>
          <div class="resource-stat-item">
            <i class="fas fa-key resource-stat-icon"></i>
            <span>Secrets: <span class="resource-stat-value">${resourceStats.secrets || 0}</span></span>
          </div>
        </div>
      </div>
      
      <div class="namespace-card-footer">
        <div class="namespace-age">
          <i class="fas fa-clock"></i>
          <span>${namespace.age || '未知'}</span>
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (!e.target.closest('.action-btn')) {
        this.showNamespaceDetail(namespace.name);
      }
    });

    return card;
  }

  // 检查是否为系统命名空间
  isSystemNamespace(name) {
    const systemNamespaces = ['default', 'kube-system', 'kube-public', 'kube-node-lease'];
    return systemNamespaces.includes(name);
  }

  // 显示命名空间详情
  async showNamespaceDetail(namespaceName) {
    if (!this.currentCluster || !namespaceName) return;

    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespaceName}`);
      const result = await response.json();

      if (result.success) {
        this.currentNamespaceDetail = result.data;
        this.displayNamespaceDetail(result.data);
        this.openDetailPanel();
      } else {
        this.showError('加载详情失败: ' + result.error);
      }
    } catch (error) {
      console.error('Failed to load namespace detail:', error);
      this.showError('加载详情失败');
    }
  }

  // 显示命名空间详情内容
  displayNamespaceDetail(namespace) {
    if (!namespace) return;

    const content = document.getElementById('namespace-detail-panel').querySelector('.detail-panel-content');
    document.getElementById('detail-namespace-name').textContent = namespace.name;

    const resourceStats = namespace.resource_stats || {};
    const labels = namespace.labels || {};
    const quotas = namespace.quotas || [];

    content.innerHTML = `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-info-circle"></i>
          基本信息
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <label>名称</label>
            <span>${namespace.name}</span>
          </div>
          <div class="detail-item">
            <label>状态</label>
            <span class="namespace-status-badge ${namespace.status?.toLowerCase() || 'active'}">${namespace.status || 'Active'}</span>
          </div>
          <div class="detail-item">
            <label>类型</label>
            <span>${this.isSystemNamespace(namespace.name) ? '系统命名空间' : '用户命名空间'}</span>
          </div>
          <div class="detail-item">
            <label>创建时间</label>
            <span>${namespace.age || '未知'}</span>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-chart-bar"></i>
          资源统计
        </div>
        <div class="detail-grid">
          <div class="detail-item">
            <label>Pods</label>
            <span>${resourceStats.pods || 0}</span>
          </div>
          <div class="detail-item">
            <label>Services</label>
            <span>${resourceStats.services || 0}</span>
          </div>
          <div class="detail-item">
            <label>ConfigMaps</label>
            <span>${resourceStats.configmaps || 0}</span>
          </div>
          <div class="detail-item">
            <label>Secrets</label>
            <span>${resourceStats.secrets || 0}</span>
          </div>
          <div class="detail-item">
            <label>PVCs</label>
            <span>${resourceStats.persistentvolumeclaims || 0}</span>
          </div>
        </div>
      </div>

      ${Object.keys(labels).length > 0 ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-tags"></i>
          标签
        </div>
        <div class="labels-container">
          ${Object.entries(labels).map(([key, value]) => 
            `<span class="label-badge">${key}=${value}</span>`
          ).join('')}
        </div>
      </div>
      ` : ''}

      ${quotas.length > 0 ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-tachometer-alt"></i>
          资源配额
        </div>
        ${quotas.map(quota => `
        <div class="detail-item">
          <label>${quota.name}</label>
          <div>
            <small>已使用: ${JSON.stringify(quota.used || {})}</small><br>
            <small>限制: ${JSON.stringify(quota.hard || {})}</small>
          </div>
        </div>
        `).join('')}
      </div>
      ` : ''}

      ${namespace.limit_ranges && namespace.limit_ranges.length > 0 ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-ruler"></i>
          限制范围
        </div>
        ${namespace.limit_ranges.map(limit => `
        <div class="detail-item">
          <label>${limit.name}</label>
          <div>
            <small>${JSON.stringify(limit.limits || {})}</small>
          </div>
        </div>
        `).join('')}
      </div>
      ` : ''}

      ${!this.isSystemNamespace(namespace.name) ? `
      <div class="detail-section">
        <div class="section-title">
          <i class="fas fa-cog"></i>
          操作
        </div>
        <div class="mt-3">
          <button class="btn btn-sm btn-outline-danger" onclick="namespacesManager.confirmDeleteNamespace('${namespace.name}')">
            <i class="fas fa-trash"></i> 删除命名空间
          </button>
        </div>
      </div>
      ` : ''}
    `;
  }

  // 显示创建模态框
  showCreateModal() {
    if (!this.currentCluster) {
      this.showError('请先选择一个集群');
      return;
    }

    document.getElementById('create-namespace-form').reset();
    this.resetLabelsContainer();
    const modal = new bootstrap.Modal(document.getElementById('create-namespace-modal'));
    modal.show();
  }

  // 确认创建
  async confirmCreate() {
    if (!this.currentCluster) {
      this.showError('请先选择一个集群');
      return;
    }

    const name = document.getElementById('namespace-name').value.trim();
    const description = document.getElementById('namespace-description').value.trim();

    if (!name) {
      this.showError('请输入命名空间名称');
      return;
    }

    // 验证名称格式
    const namePattern = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
    if (!namePattern.test(name)) {
      this.showError('命名空间名称格式无效。只能包含小写字母、数字和连字符，且不能以连字符开头或结尾。');
      return;
    }

    const labels = this.collectLabels();
    if (description) {
      labels['description'] = description;
    }

    const data = {
      name: name,
      labels: labels
    };

    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      const result = await response.json();

      if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('create-namespace-modal')).hide();
        this.showSuccess('命名空间创建成功');
        this.loadNamespaces();
      } else {
        this.showError('创建失败: ' + (result.error || '未知错误'));
      }
    } catch (error) {
      console.error('Failed to create namespace:', error);
      this.showError('创建命名空间失败: ' + error.message);
    }
  }

  // 标签管理
  resetLabelsContainer() {
    const container = document.getElementById('labels-container');
    container.innerHTML = `
      <div class="input-group mb-2">
        <input type="text" class="form-control label-key" placeholder="键">
        <span class="input-group-text">=</span>
        <input type="text" class="form-control label-value" placeholder="值">
        <button type="button" class="btn btn-outline-secondary add-label-btn">
          <i class="fas fa-plus"></i>
        </button>
      </div>
    `;
  }

  addLabelRow() {
    const container = document.getElementById('labels-container');
    const newRow = document.createElement('div');
    newRow.className = 'input-group mb-2';
    newRow.innerHTML = `
      <input type="text" class="form-control label-key" placeholder="键">
      <span class="input-group-text">=</span>
      <input type="text" class="form-control label-value" placeholder="值">
      <button type="button" class="btn btn-outline-danger remove-label-btn">
        <i class="fas fa-minus"></i>
      </button>
    `;
    container.appendChild(newRow);
  }

  removeLabelRow(button) {
    const row = button.closest('.input-group');
    if (row) {
      row.remove();
    }
  }

  collectLabels() {
    const labels = {};
    const container = document.getElementById('labels-container');
    const rows = container.querySelectorAll('.input-group');

    rows.forEach(row => {
      const key = row.querySelector('.label-key').value.trim();
      const value = row.querySelector('.label-value').value.trim();

      if (key && value) {
        labels[key] = value;
      }
    });

    return labels;
  }

  // 确认删除命名空间
  confirmDeleteNamespace(namespaceName) {
    if (this.isSystemNamespace(namespaceName)) {
      this.showError('不能删除系统命名空间');
      return;
    }

    if (confirm(`确定要删除命名空间 "${namespaceName}" 吗？\n\n警告：这将删除命名空间中的所有资源，且无法恢复！`)) {
      this.deleteNamespace(namespaceName);
    }
  }

  // 删除命名空间
  async deleteNamespace(namespaceName) {
    if (!this.currentCluster || !namespaceName) return;

    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${namespaceName}`, {
        method: 'DELETE'
      });

      const result = await response.json();

      if (result.success) {
        this.showSuccess('命名空间删除请求已提交，正在后台处理...');
        this.closeDetailPanel();
        this.loadNamespaces();
      } else {
        this.showError('删除失败: ' + (result.error || '未知错误'));
      }
    } catch (error) {
      console.error('Failed to delete namespace:', error);
      this.showError('删除命名空间失败: ' + error.message);
    }
  }

  // 更新统计
  updateStats() {
    const stats = {
      active: 0,
      user: 0,
      system: 0,
      terminating: 0
    };

    this.namespaces.forEach(namespace => {
      // 状态统计
      if (namespace.status === 'Active' || !namespace.status) {
        stats.active++;
      } else if (namespace.status === 'Terminating') {
        stats.terminating++;
      }

      // 类型统计
      if (this.isSystemNamespace(namespace.name)) {
        stats.system++;
      } else {
        stats.user++;
      }
    });

    document.getElementById('activeNamespacesCount').textContent = stats.active;
    document.getElementById('userNamespacesCount').textContent = stats.user;
    document.getElementById('systemNamespacesCount').textContent = stats.system;
    document.getElementById('terminatingNamespacesCount').textContent = stats.terminating;
  }

  // 更新分页
  updatePagination() {
    const totalPages = Math.ceil(this.filteredNamespaces.length / this.itemsPerPage);
    
    if (totalPages <= 1) {
      document.getElementById('pagination-section').style.display = 'none';
      return;
    }

    document.getElementById('pagination-section').style.display = 'flex';
    
    const startIndex = (this.currentPage - 1) * this.itemsPerPage + 1;
    const endIndex = Math.min(this.currentPage * this.itemsPerPage, this.filteredNamespaces.length);
    
    document.getElementById('items-range').textContent = `${startIndex}-${endIndex}`;
    document.getElementById('total-items').textContent = this.filteredNamespaces.length;

    // 生成分页控件
    const controls = document.getElementById('pagination-controls');
    controls.innerHTML = '';

    // 上一页
    const prevBtn = document.createElement('li');
    prevBtn.className = `page-item ${this.currentPage === 1 ? 'disabled' : ''}`;
    prevBtn.innerHTML = `
      <a class="page-link" href="#" onclick="namespacesManager.goToPage(${this.currentPage - 1})">
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
        <a class="page-link" href="#" onclick="namespacesManager.goToPage(${i})">${i}</a>
      `;
      controls.appendChild(pageBtn);
    }

    // 下一页
    const nextBtn = document.createElement('li');
    nextBtn.className = `page-item ${this.currentPage === totalPages ? 'disabled' : ''}`;
    nextBtn.innerHTML = `
      <a class="page-link" href="#" onclick="namespacesManager.goToPage(${this.currentPage + 1})">
        <i class="fas fa-chevron-right"></i>
      </a>
    `;
    controls.appendChild(nextBtn);
  }

  // 跳转页面
  goToPage(page) {
    const totalPages = Math.ceil(this.filteredNamespaces.length / this.itemsPerPage);
    
    if (page >= 1 && page <= totalPages) {
      this.currentPage = page;
      this.displayNamespaces();
    }
  }

  // 打开详情面板
  openDetailPanel() {
    document.getElementById('namespace-detail-panel').classList.add('open');
  }

  // 关闭详情面板
  closeDetailPanel() {
    document.getElementById('namespace-detail-panel').classList.remove('open');
  }

  // 显示状态管理
  showLoadingState() {
    console.log('Loading namespaces...');
    // TODO: 可以添加加载动画
  }

  showEmptyState() {
    const container = document.getElementById('namespaces-cards-container');
    container.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-layer-group fa-3x"></i>
        <h5>暂无命名空间</h5>
        <p>请先选择一个集群查看命名空间</p>
      </div>
    `;
  }

  showEmptyNamespaces() {
    const container = document.getElementById('namespaces-cards-container');
    container.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-layer-group fa-3x"></i>
        <h5>暂无命名空间</h5>
        <p>当前过滤条件下没有找到命名空间</p>
      </div>
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

  // 初始化自动刷新
  initAutoRefresh() {
    // 使用全局自动刷新组件
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        if (this.currentCluster) {
          this.loadNamespaces();
        }
      }, {
        defaultInterval: 30000,
        storageKey: 'autoRefreshSettings_namespaces'
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

// 全局实例
let namespacesManager;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  namespacesManager = new NamespacesManager();
});