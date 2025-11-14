/**
 * 自动刷新功能集成指南
 * 
 * 此文件展示如何在各个页面管理器中集成自动刷新功能
 * 这是一个示例文件，不会被实际使用
 */

// ===== 示例1: 基本集成模式 =====
class ExamplePageManager {
  constructor() {
    this.autoRefreshManager = null;
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadData();
    this.initAutoRefresh(); // 🔑 关键：初始化自动刷新
  }

  // 🔑 必须实现：初始化自动刷新
  initAutoRefresh() {
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        // 🔑 这里调用您页面的数据加载方法
        this.loadData();
      }, {
        defaultInterval: 30000, // 默认30秒
        storageKey: 'autoRefreshSettings_yourPage' // 🔑 每个页面使用唯一的存储键
      });
    }
  }

  // 🔑 手动刷新时必须调用：通知自动刷新管理器
  handleManualRefresh() {
    this.loadData();
    
    // 🔑 重要：告知自动刷新管理器手动刷新已执行
    if (typeof notifyManualRefresh === 'function') {
      notifyManualRefresh();
    }
  }

  // 🔑 页面销毁时清理
  destroy() {
    if (this.autoRefreshManager) {
      this.autoRefreshManager.destroy();
      this.autoRefreshManager = null;
    }
  }

  loadData() {
    // 您的数据加载逻辑
    console.log('Loading data...');
  }
}

// ===== 示例2: 带条件判断的集成模式 =====
class ConditionalRefreshManager {
  constructor() {
    this.currentCluster = null;
    this.autoRefreshManager = null;
    this.init();
  }

  init() {
    this.bindEvents();
    this.initAutoRefresh();
  }

  initAutoRefresh() {
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        // 🔑 只有在满足条件时才刷新
        if (this.currentCluster && this.shouldAutoRefresh()) {
          this.loadData();
        }
      }, {
        defaultInterval: 15000, // 更频繁的刷新
        storageKey: 'autoRefreshSettings_conditional'
      });
    }
  }

  shouldAutoRefresh() {
    // 自定义刷新条件
    return this.currentCluster !== null && 
           document.visibilityState === 'visible';
  }

  loadData() {
    if (!this.currentCluster) {
      console.log('No cluster selected');
      return;
    }
    console.log('Loading data for cluster:', this.currentCluster);
  }
}

// ===== 示例3: 多数据源的集成模式 =====
class MultiSourceManager {
  constructor() {
    this.autoRefreshManager = null;
    this.init();
  }

  init() {
    this.initAutoRefresh();
  }

  initAutoRefresh() {
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(() => {
        // 🔑 可以在一次刷新中加载多个数据源
        Promise.all([
          this.loadPrimaryData(),
          this.loadSecondaryData(),
          this.loadStatistics()
        ]).catch(error => {
          console.error('Auto-refresh failed:', error);
        });
      }, {
        defaultInterval: 60000, // 1分钟刷新
        storageKey: 'autoRefreshSettings_multiSource'
      });
    }
  }

  async loadPrimaryData() {
    console.log('Loading primary data...');
  }

  async loadSecondaryData() {
    console.log('Loading secondary data...');
  }

  async loadStatistics() {
    console.log('Loading statistics...');
  }
}

// ===== 示例4: 高级自定义配置 =====
class AdvancedRefreshManager {
  constructor() {
    this.autoRefreshManager = null;
    this.init();
  }

  init() {
    this.initAutoRefresh();
  }

  initAutoRefresh() {
    if (typeof initAutoRefresh === 'function') {
      this.autoRefreshManager = initAutoRefresh(
        this.customRefreshCallback.bind(this), // 🔑 使用自定义回调
        {
          defaultInterval: 45000,
          minInterval: 10000,    // 🔑 自定义最小间隔
          maxInterval: 600000,   // 🔑 自定义最大间隔
          storageKey: 'autoRefreshSettings_advanced'
        }
      );
    }
  }

  customRefreshCallback() {
    // 🔑 自定义刷新逻辑
    const now = new Date();
    const isBusinessHours = now.getHours() >= 9 && now.getHours() <= 18;
    
    if (isBusinessHours) {
      // 工作时间更频繁刷新
      this.loadCriticalData();
    } else {
      // 非工作时间只刷新基本数据
      this.loadBasicData();
    }
  }

  loadCriticalData() {
    console.log('Loading critical data during business hours...');
  }

  loadBasicData() {
    console.log('Loading basic data during off hours...');
  }
}

// ===== 使用说明 =====
/**
 * 集成步骤:
 * 
 * 1. 在您的页面管理器构造函数中添加:
 *    this.autoRefreshManager = null;
 * 
 * 2. 在init()方法中调用:
 *    this.initAutoRefresh();
 * 
 * 3. 实现initAutoRefresh()方法:
 *    initAutoRefresh() {
 *      if (typeof initAutoRefresh === 'function') {
 *        this.autoRefreshManager = initAutoRefresh(() => {
 *          this.yourDataLoadMethod();
 *        }, {
 *          defaultInterval: 30000,
 *          storageKey: 'autoRefreshSettings_yourPage'
 *        });
 *      }
 *    }
 * 
 * 4. 在手动刷新方法中添加通知:
 *    if (typeof notifyManualRefresh === 'function') {
 *      notifyManualRefresh();
 *    }
 * 
 * 5. 在页面销毁时清理:
 *    if (this.autoRefreshManager) {
 *      this.autoRefreshManager.destroy();
 *    }
 * 
 * 功能特性:
 * - ✅ 可配置刷新间隔 (5秒 - 5分钟)
 * - ✅ 开关控制启用/禁用
 * - ✅ 页面失焦时自动暂停
 * - ✅ 倒计时显示
 * - ✅ 设置持久化保存
 * - ✅ 键盘快捷键支持 (Ctrl+Shift+R)
 * - ✅ 响应式设计
 * - ✅ 批量操作时智能暂停
 * 
 * 每个页面的存储键建议:
 * - 节点管理: 'autoRefreshSettings_nodes'
 * - Pod管理: 'autoRefreshSettings_pods'  
 * - 命名空间: 'autoRefreshSettings_namespaces'
 * - 工作负载: 'autoRefreshSettings_workloads'
 * - 集群管理: 'autoRefreshSettings_clusters'
 * - 实例管理: 'autoRefreshSettings_instances'
 * - 卷管理: 'autoRefreshSettings_volumes'
 */

console.log('📚 Auto-refresh integration guide loaded');