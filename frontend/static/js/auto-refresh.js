/**
 * 通用自动刷新组件
 * 支持多页面使用，可配置刷新间隔
 */

class AutoRefreshManager {
  constructor(options = {}) {
    this.refreshCallback = options.refreshCallback || null;
    this.defaultInterval = options.defaultInterval || 30000; // 默认30秒
    this.minInterval = options.minInterval || 5000; // 最小5秒
    this.maxInterval = options.maxInterval || 300000; // 最大5分钟
    this.storageKey = options.storageKey || 'autoRefreshSettings';
    
    this.isEnabled = false;
    this.currentInterval = this.defaultInterval;
    this.intervalId = null;
    this.lastRefreshTime = null;
    this.isPaused = false;
    
    // UI元素
    this.refreshButton = null;
    this.settingsPanel = null;
    this.statusIndicator = null;
    
    this.init();
  }

  init() {
    this.loadSettings();
    this.createUI();
    this.bindEvents();
    this.updateUI();
    
    // 如果设置为启用，启动自动刷新
    if (this.isEnabled) {
      this.start();
    }
  }

  // 加载保存的设置
  loadSettings() {
    try {
      const settings = localStorage.getItem(this.storageKey);
      if (settings) {
        const parsed = JSON.parse(settings);
        this.isEnabled = parsed.enabled || false;
        this.currentInterval = Math.max(this.minInterval, 
          Math.min(this.maxInterval, parsed.interval || this.defaultInterval));
      }
    } catch (error) {
      console.warn('Failed to load auto-refresh settings:', error);
    }
  }

  // 保存设置
  saveSettings() {
    try {
      const settings = {
        enabled: this.isEnabled,
        interval: this.currentInterval
      };
      localStorage.setItem(this.storageKey, JSON.stringify(settings));
    } catch (error) {
      console.warn('Failed to save auto-refresh settings:', error);
    }
  }

  // 创建UI组件
  createUI() {
    // 查找现有的刷新按钮
    this.refreshButton = document.querySelector('#refresh-btn, [id*="refresh"], .refresh-btn');
    
    if (!this.refreshButton) {
      console.warn('No refresh button found, auto-refresh UI will not be available');
      return;
    }

    // 在刷新按钮旁边添加自动刷新控件
    this.createAutoRefreshControls();
  }

  createAutoRefreshControls() {
    // 创建容器
    const container = document.createElement('div');
    container.className = 'auto-refresh-container';
    container.innerHTML = `
      <div class="auto-refresh-controls">
        <!-- 自动刷新开关 -->
        <div class="auto-refresh-toggle">
          <label class="auto-refresh-switch">
            <input type="checkbox" id="auto-refresh-checkbox" ${this.isEnabled ? 'checked' : ''}>
            <span class="slider"></span>
          </label>
          <span class="auto-refresh-label">自动刷新</span>
        </div>
        
        <!-- 状态指示器 -->
        <div class="auto-refresh-status" id="auto-refresh-status">
          <span class="status-text">已停止</span>
          <span class="countdown" id="refresh-countdown"></span>
        </div>
        
        <!-- 设置按钮 -->
        <button class="btn btn-sm btn-outline-secondary auto-refresh-settings-btn" 
                id="auto-refresh-settings-btn" 
                title="自动刷新设置">
          <i class="fas fa-cog"></i>
        </button>
      </div>
      
      <!-- 设置面板 -->
      <div class="auto-refresh-settings-panel" id="auto-refresh-settings-panel" style="display: none;">
        <div class="settings-panel-content">
          <h6><i class="fas fa-cog"></i> 自动刷新设置</h6>
          
          <div class="setting-item">
            <label for="refresh-interval-select">刷新间隔:</label>
            <select class="form-select form-select-sm" id="refresh-interval-select">
              <option value="5000">5秒</option>
              <option value="10000">10秒</option>
              <option value="15000">15秒</option>
              <option value="30000" selected>30秒</option>
              <option value="60000">1分钟</option>
              <option value="120000">2分钟</option>
              <option value="300000">5分钟</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          
          <div class="setting-item" id="custom-interval-setting" style="display: none;">
            <label for="custom-interval-input">自定义间隔(秒):</label>
            <input type="number" class="form-control form-control-sm" 
                   id="custom-interval-input" 
                   min="5" max="300" step="5" value="30">
          </div>
          
          <div class="setting-item">
            <div class="form-check">
              <input class="form-check-input" type="checkbox" id="pause-on-blur" checked>
              <label class="form-check-label" for="pause-on-blur">
                页面失焦时暂停
              </label>
            </div>
          </div>
          
          <div class="setting-item">
            <div class="form-check">
              <input class="form-check-input" type="checkbox" id="show-countdown" checked>
              <label class="form-check-label" for="show-countdown">
                显示倒计时
              </label>
            </div>
          </div>
          
          <div class="settings-actions">
            <button class="btn btn-sm btn-primary" id="apply-settings-btn">应用</button>
            <button class="btn btn-sm btn-secondary" id="cancel-settings-btn">取消</button>
          </div>
        </div>
      </div>
    `;

    // 插入到刷新按钮旁边
    this.refreshButton.parentNode.insertBefore(container, this.refreshButton.nextSibling);
    
    // 获取UI元素引用
    this.statusIndicator = document.getElementById('auto-refresh-status');
    this.settingsPanel = document.getElementById('auto-refresh-settings-panel');
  }

  // 绑定事件
  bindEvents() {
    // 自动刷新开关
    const checkbox = document.getElementById('auto-refresh-checkbox');
    if (checkbox) {
      checkbox.addEventListener('change', this.handleToggle.bind(this));
    }

    // 设置按钮
    const settingsBtn = document.getElementById('auto-refresh-settings-btn');
    if (settingsBtn) {
      settingsBtn.addEventListener('click', this.toggleSettingsPanel.bind(this));
    }

    // 间隔选择
    const intervalSelect = document.getElementById('refresh-interval-select');
    if (intervalSelect) {
      intervalSelect.addEventListener('change', this.handleIntervalChange.bind(this));
      intervalSelect.value = this.currentInterval.toString();
    }

    // 自定义间隔输入
    const customInput = document.getElementById('custom-interval-input');
    if (customInput) {
      customInput.addEventListener('input', this.handleCustomIntervalInput.bind(this));
    }

    // 设置面板按钮
    const applyBtn = document.getElementById('apply-settings-btn');
    if (applyBtn) {
      applyBtn.addEventListener('click', this.applySettings.bind(this));
    }

    const cancelBtn = document.getElementById('cancel-settings-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', this.cancelSettings.bind(this));
    }

    // 页面可见性变化
    document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));

    // 点击外部关闭设置面板
    document.addEventListener('click', this.handleOutsideClick.bind(this));

    // 键盘快捷键
    document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
  }

  // 设置刷新回调函数
  setRefreshCallback(callback) {
    this.refreshCallback = callback;
  }

  // 启动自动刷新
  start() {
    if (this.intervalId) {
      this.stop();
    }

    this.isEnabled = true;
    this.isPaused = false;
    this.lastRefreshTime = Date.now();
    
    this.intervalId = setInterval(() => {
      if (!this.isPaused && document.visibilityState === 'visible') {
        this.executeRefresh();
      }
    }, this.currentInterval);

    this.updateUI();
    this.saveSettings();
    this.startCountdown();
  }

  // 停止自动刷新
  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }

    this.isEnabled = false;
    this.isPaused = false;
    this.updateUI();
    this.saveSettings();
    this.stopCountdown();
  }

  // 暂停自动刷新
  pause() {
    this.isPaused = true;
    this.updateUI();
    this.stopCountdown();
  }

  // 恢复自动刷新
  resume() {
    this.isPaused = false;
    this.lastRefreshTime = Date.now();
    this.updateUI();
    this.startCountdown();
  }

  // 执行刷新
  executeRefresh() {
    this.lastRefreshTime = Date.now();
    
    if (this.refreshCallback && typeof this.refreshCallback === 'function') {
      try {
        this.refreshCallback();
      } catch (error) {
        console.error('Auto-refresh callback error:', error);
      }
    }
    
    // 重启倒计时
    this.startCountdown();
  }

  // 启动倒计时
  startCountdown() {
    this.stopCountdown();
    
    const showCountdown = document.getElementById('show-countdown')?.checked !== false;
    if (!showCountdown || !this.isEnabled || this.isPaused) {
      return;
    }

    const countdownElement = document.getElementById('refresh-countdown');
    if (!countdownElement) return;

    this.countdownIntervalId = setInterval(() => {
      if (this.isPaused || !this.isEnabled) {
        this.stopCountdown();
        return;
      }

      const elapsed = Date.now() - this.lastRefreshTime;
      const remaining = Math.max(0, this.currentInterval - elapsed);
      
      if (remaining === 0) {
        countdownElement.textContent = '';
        return;
      }

      const seconds = Math.ceil(remaining / 1000);
      countdownElement.textContent = `${seconds}s`;
    }, 1000);
  }

  // 停止倒计时
  stopCountdown() {
    if (this.countdownIntervalId) {
      clearInterval(this.countdownIntervalId);
      this.countdownIntervalId = null;
    }
    
    const countdownElement = document.getElementById('refresh-countdown');
    if (countdownElement) {
      countdownElement.textContent = '';
    }
  }

  // 更新UI状态
  updateUI() {
    const checkbox = document.getElementById('auto-refresh-checkbox');
    const statusText = this.statusIndicator?.querySelector('.status-text');
    
    if (checkbox) {
      checkbox.checked = this.isEnabled;
    }

    if (statusText) {
      if (this.isEnabled) {
        if (this.isPaused) {
          statusText.textContent = '已暂停';
          statusText.className = 'status-text status-paused';
        } else {
          statusText.textContent = '运行中';
          statusText.className = 'status-text status-active';
        }
      } else {
        statusText.textContent = '已停止';
        statusText.className = 'status-text status-stopped';
      }
    }

    // 更新工具提示
    if (this.refreshButton) {
      const oldTitle = this.refreshButton.getAttribute('title') || '';
      if (this.isEnabled) {
        this.refreshButton.setAttribute('title', `手动刷新 (自动刷新: ${this.currentInterval/1000}s)`);
      } else {
        this.refreshButton.setAttribute('title', '手动刷新');
      }
    }
  }

  // 事件处理函数
  handleToggle(event) {
    if (event.target.checked) {
      this.start();
    } else {
      this.stop();
    }
  }

  handleIntervalChange(event) {
    const value = event.target.value;
    const customSetting = document.getElementById('custom-interval-setting');
    
    if (value === 'custom') {
      if (customSetting) customSetting.style.display = 'block';
    } else {
      if (customSetting) customSetting.style.display = 'none';
      this.currentInterval = parseInt(value);
    }
  }

  handleCustomIntervalInput(event) {
    const value = parseInt(event.target.value);
    if (value >= this.minInterval / 1000 && value <= this.maxInterval / 1000) {
      this.currentInterval = value * 1000;
    }
  }

  toggleSettingsPanel() {
    if (this.settingsPanel) {
      const isVisible = this.settingsPanel.style.display !== 'none';
      this.settingsPanel.style.display = isVisible ? 'none' : 'block';
      
      if (!isVisible) {
        // 同步当前设置到UI
        this.syncSettingsToUI();
      }
    }
  }

  syncSettingsToUI() {
    const intervalSelect = document.getElementById('refresh-interval-select');
    const customInput = document.getElementById('custom-interval-input');
    const customSetting = document.getElementById('custom-interval-setting');
    
    if (intervalSelect) {
      const standardValues = ['5000', '10000', '15000', '30000', '60000', '120000', '300000'];
      if (standardValues.includes(this.currentInterval.toString())) {
        intervalSelect.value = this.currentInterval.toString();
        if (customSetting) customSetting.style.display = 'none';
      } else {
        intervalSelect.value = 'custom';
        if (customSetting) customSetting.style.display = 'block';
        if (customInput) customInput.value = this.currentInterval / 1000;
      }
    }
  }

  applySettings() {
    const intervalSelect = document.getElementById('refresh-interval-select');
    const customInput = document.getElementById('custom-interval-input');
    
    // 获取新的间隔时间
    let newInterval = this.currentInterval;
    if (intervalSelect?.value === 'custom') {
      const customValue = parseInt(customInput?.value || '30');
      newInterval = Math.max(this.minInterval / 1000, 
        Math.min(this.maxInterval / 1000, customValue)) * 1000;
    } else if (intervalSelect?.value) {
      newInterval = parseInt(intervalSelect.value);
    }

    // 如果间隔改变了且自动刷新正在运行，重新启动
    if (newInterval !== this.currentInterval) {
      this.currentInterval = newInterval;
      if (this.isEnabled) {
        this.start(); // 重新启动以应用新间隔
      }
    }

    this.saveSettings();
    this.toggleSettingsPanel();
    this.updateUI();
    
    this.showNotification(`自动刷新设置已更新：${this.currentInterval/1000}秒间隔`, 'success');
  }

  cancelSettings() {
    this.toggleSettingsPanel();
    this.syncSettingsToUI(); // 恢复到原始设置
  }

  handleVisibilityChange() {
    const pauseOnBlur = document.getElementById('pause-on-blur')?.checked !== false;
    
    if (pauseOnBlur && this.isEnabled) {
      if (document.visibilityState === 'hidden') {
        this.pause();
      } else if (document.visibilityState === 'visible' && this.isPaused) {
        this.resume();
      }
    }
  }

  handleOutsideClick(event) {
    if (this.settingsPanel && 
        this.settingsPanel.style.display === 'block' &&
        !this.settingsPanel.contains(event.target) &&
        !document.getElementById('auto-refresh-settings-btn')?.contains(event.target)) {
      this.toggleSettingsPanel();
    }
  }

  handleKeyboardShortcuts(event) {
    // Ctrl/Cmd + Shift + R: 切换自动刷新
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === 'R') {
      event.preventDefault();
      const checkbox = document.getElementById('auto-refresh-checkbox');
      if (checkbox) {
        checkbox.checked = !checkbox.checked;
        this.handleToggle({ target: checkbox });
      }
    }
  }

  // 手动触发刷新（更新最后刷新时间）
  manualRefresh() {
    this.lastRefreshTime = Date.now();
    this.startCountdown();
  }

  // 获取状态信息
  getStatus() {
    return {
      enabled: this.isEnabled,
      paused: this.isPaused,
      interval: this.currentInterval,
      timeUntilNext: this.isEnabled && !this.isPaused ? 
        Math.max(0, this.currentInterval - (Date.now() - this.lastRefreshTime)) : null
    };
  }

  // 显示通知
  showNotification(message, type = 'info') {
    // 简单的通知实现，可以被页面特定的通知系统覆盖
    if (window.showNotification && typeof window.showNotification === 'function') {
      window.showNotification(message, type);
      return;
    }

    // 备用通知
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
    notification.style.cssText = `
      position: fixed; 
      top: 20px; 
      right: 20px; 
      z-index: 9999; 
      min-width: 300px;
      animation: slideInRight 0.3s ease;
    `;
    notification.innerHTML = `
      ${message}
      <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, type === 'error' ? 8000 : 4000);
  }

  // 销毁实例
  destroy() {
    this.stop();
    
    const container = document.querySelector('.auto-refresh-container');
    if (container) {
      container.remove();
    }
    
    document.removeEventListener('visibilitychange', this.handleVisibilityChange);
    document.removeEventListener('click', this.handleOutsideClick);
    document.removeEventListener('keydown', this.handleKeyboardShortcuts);
  }
}

// 全局自动刷新管理器实例
let globalAutoRefreshManager = null;

// 初始化自动刷新功能
function initAutoRefresh(refreshCallback, options = {}) {
  // 如果已经有实例，先销毁
  if (globalAutoRefreshManager) {
    globalAutoRefreshManager.destroy();
  }
  
  // 创建新实例
  globalAutoRefreshManager = new AutoRefreshManager({
    refreshCallback: refreshCallback,
    ...options
  });
  
  return globalAutoRefreshManager;
}

// 获取全局自动刷新管理器
function getAutoRefreshManager() {
  return globalAutoRefreshManager;
}

// 手动刷新时通知自动刷新管理器
function notifyManualRefresh() {
  if (globalAutoRefreshManager) {
    globalAutoRefreshManager.manualRefresh();
  }
}

// 导出给全局使用
if (typeof window !== 'undefined') {
  window.AutoRefreshManager = AutoRefreshManager;
  window.initAutoRefresh = initAutoRefresh;
  window.getAutoRefreshManager = getAutoRefreshManager;
  window.notifyManualRefresh = notifyManualRefresh;
}

// 添加CSS样式
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    /* 自动刷新组件样式 */
    .auto-refresh-container {
      display: inline-flex;
      align-items: center;
      gap: 1rem;
      margin-left: 1rem;
      position: relative;
    }

    .auto-refresh-controls {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    /* 开关样式 */
    .auto-refresh-toggle {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .auto-refresh-switch {
      position: relative;
      display: inline-block;
      width: 40px;
      height: 20px;
      cursor: pointer;
    }

    .auto-refresh-switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: #ccc;
      transition: 0.3s;
      border-radius: 20px;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 2px;
      bottom: 2px;
      background-color: white;
      transition: 0.3s;
      border-radius: 50%;
    }

    input:checked + .slider {
      background-color: #28a745;
    }

    input:checked + .slider:before {
      transform: translateX(20px);
    }

    .auto-refresh-label {
      font-size: 0.9rem;
      color: #6c757d;
      font-weight: 500;
      white-space: nowrap;
    }

    /* 状态指示器 */
    .auto-refresh-status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
    }

    .status-text {
      font-weight: 500;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.8rem;
    }

    .status-text.status-active {
      background: #d1e7dd;
      color: #0f5132;
    }

    .status-text.status-paused {
      background: #fff3cd;
      color: #856404;
    }

    .status-text.status-stopped {
      background: #f8d7da;
      color: #721c24;
    }

    .countdown {
      font-family: 'Courier New', monospace;
      font-weight: 600;
      color: #0d6efd;
      min-width: 30px;
      text-align: center;
    }

    /* 设置面板 */
    .auto-refresh-settings-panel {
      position: absolute;
      top: 100%;
      right: 0;
      width: 280px;
      background: white;
      border: 1px solid #dee2e6;
      border-radius: 8px;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
      z-index: 1000;
      margin-top: 0.5rem;
    }

    .settings-panel-content {
      padding: 1rem;
    }

    .settings-panel-content h6 {
      margin-bottom: 1rem;
      color: #495057;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .setting-item {
      margin-bottom: 1rem;
    }

    .setting-item:last-child {
      margin-bottom: 0;
    }

    .setting-item label {
      display: block;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      font-weight: 500;
      color: #495057;
    }

    .settings-actions {
      display: flex;
      gap: 0.5rem;
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 1px solid #dee2e6;
    }

    .settings-actions .btn {
      flex: 1;
    }

    /* 响应式 */
    @media (max-width: 768px) {
      .auto-refresh-container {
        flex-direction: column;
        align-items: flex-end;
        gap: 0.5rem;
        margin-left: 0;
        margin-top: 0.5rem;
      }
      
      .auto-refresh-controls {
        gap: 0.5rem;
      }
      
      .auto-refresh-label {
        font-size: 0.8rem;
      }
      
      .auto-refresh-settings-panel {
        width: 260px;
        right: -50px;
      }
    }

    /* 动画 */
    @keyframes slideInRight {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }

    /* 增强现有刷新按钮样式 */
    .auto-refresh-container + .btn[id*="refresh"] i,
    .auto-refresh-container ~ .btn[id*="refresh"] i {
      transition: transform 0.3s ease;
    }

    .auto-refresh-container + .btn[id*="refresh"]:hover i,
    .auto-refresh-container ~ .btn[id*="refresh"]:hover i {
      transform: rotate(90deg);
    }
  `;
  
  document.head.appendChild(style);
}

console.log('🔄 Auto-refresh component loaded successfully');