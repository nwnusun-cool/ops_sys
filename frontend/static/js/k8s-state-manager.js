/**
 * K8s页面状态管理器
 * 用于保存和恢复页面状态，包括集群选择、命名空间选择等
 */
class K8sStateManager {
  constructor(pageId) {
    this.pageId = pageId;
    this.storageKey = `k8s_state_${pageId}`;
    this.defaultState = {
      clusterId: '',
      namespace: '',
      filters: {},
      lastUpdated: null
    };
  }

  /**
   * 保存当前页面状态
   * @param {Object} state - 要保存的状态对象
   */
  saveState(state) {
    try {
      const stateToSave = {
        ...state,
        lastUpdated: Date.now()
      };
      localStorage.setItem(this.storageKey, JSON.stringify(stateToSave));
      console.log(`🔄 已保存 ${this.pageId} 页面状态:`, stateToSave);
    } catch (error) {
      console.error(`❌ 保存 ${this.pageId} 页面状态失败:`, error);
    }
  }

  /**
   * 加载页面状态
   * @returns {Object} 加载的状态对象
   */
  loadState() {
    try {
      const savedState = localStorage.getItem(this.storageKey);
      if (savedState) {
        const state = JSON.parse(savedState);
        // 检查状态是否过期（1小时过期）
        const oneHourAgo = Date.now() - (60 * 60 * 1000);
        if (state.lastUpdated && state.lastUpdated > oneHourAgo) {
          console.log(`✅ 加载 ${this.pageId} 页面状态:`, state);
          return { ...this.defaultState, ...state };
        } else {
          console.log(`⚠️ ${this.pageId} 页面状态已过期，使用默认状态`);
        }
      }
    } catch (error) {
      console.error(`❌ 加载 ${this.pageId} 页面状态失败:`, error);
    }
    return { ...this.defaultState };
  }

  /**
   * 清除页面状态
   */
  clearState() {
    try {
      localStorage.removeItem(this.storageKey);
      console.log(`🗑️ 已清除 ${this.pageId} 页面状态`);
    } catch (error) {
      console.error(`❌ 清除 ${this.pageId} 页面状态失败:`, error);
    }
  }

  /**
   * 更新特定字段的状态
   * @param {string} key - 要更新的字段名
   * @param {any} value - 新的值
   */
  updateStateField(key, value) {
    const currentState = this.loadState();
    const newState = { ...currentState, [key]: value };
    this.saveState(newState);
  }

  /**
   * 获取特定字段的状态值
   * @param {string} key - 字段名
   * @param {any} defaultValue - 默认值
   * @returns {any} 字段值
   */
  getStateField(key, defaultValue = null) {
    const state = this.loadState();
    return state[key] !== undefined ? state[key] : defaultValue;
  }
}

/**
 * K8s页面通用辅助函数
 */
class K8sPageHelper {
  /**
   * 恢复选择框的状态
   * @param {string} selectId - 选择框的ID
   * @param {string} value - 要设置的值
   * @param {function} callback - 值改变后的回调函数
   */
  static async restoreSelectValue(selectId, value, callback = null) {
    const select = document.getElementById(selectId);
    if (!select || !value) return;

    // 等待选择框选项加载完成
    let attempts = 0;
    const maxAttempts = 50; // 最多等待5秒

    const tryRestore = () => {
      const option = select.querySelector(`option[value="${value}"]`);
      if (option) {
        select.value = value;
        console.log(`✅ 恢复 ${selectId} 的值: ${value}`);
        // 触发change事件
        const event = new Event('change', { bubbles: true });
        select.dispatchEvent(event);
        if (callback) callback(value);
        return true;
      }
      return false;
    };

    // 如果选项已经存在，直接恢复
    if (tryRestore()) return;

    // 否则等待选项加载
    const interval = setInterval(() => {
      attempts++;
      if (tryRestore() || attempts >= maxAttempts) {
        clearInterval(interval);
        if (attempts >= maxAttempts) {
          console.warn(`⚠️ 恢复 ${selectId} 的值超时: ${value}`);
        }
      }
    }, 100);
  }

  /**
   * 创建状态保存的事件监听器
   * @param {K8sStateManager} stateManager - 状态管理器
   * @param {string} selectId - 选择框ID
   * @param {string} stateKey - 状态字段名
   */
  static bindStateSaveListener(stateManager, selectId, stateKey) {
    const select = document.getElementById(selectId);
    if (select) {
      select.addEventListener('change', function() {
        stateManager.updateStateField(stateKey, this.value);
      });
    }
  }

  /**
   * 显示通知消息
   * @param {string} message - 消息内容
   * @param {string} type - 消息类型: success, error, warning, info
   */
  static showNotification(message, type = 'info') {
    if (window.showNotification) {
      window.showNotification(message, type);
    } else {
      console.log(`[${type.toUpperCase()}] ${message}`);
    }
  }

  /**
   * 等待元素出现
   * @param {string} selector - CSS选择器
   * @param {number} timeout - 超时时间(毫秒)
   * @returns {Promise<Element>} 找到的元素
   */
  static waitForElement(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
      const element = document.querySelector(selector);
      if (element) {
        resolve(element);
        return;
      }

      const observer = new MutationObserver((mutations, obs) => {
        const element = document.querySelector(selector);
        if (element) {
          obs.disconnect();
          resolve(element);
        }
      });

      observer.observe(document, {
        childList: true,
        subtree: true
      });

      setTimeout(() => {
        observer.disconnect();
        reject(new Error(`元素 ${selector} 在 ${timeout}ms 内未找到`));
      }, timeout);
    });
  }
}

// 全局导出
window.K8sStateManager = K8sStateManager;
window.K8sPageHelper = K8sPageHelper;

console.log('✅ K8s状态管理器加载完成');