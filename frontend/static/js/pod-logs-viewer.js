/**
 * Pod实时日志查看器组件
 * 提供实时日志流显示、搜索、过滤、下载等功能
 */

class PodLogsViewer {
  constructor() {
    this.currentPod = null;
    this.currentNamespace = null;
    this.currentCluster = null;
    this.currentContainer = null;
    this.isStreaming = false;
    this.logBuffer = [];
    this.maxBufferSize = 10000; // 最大缓存行数
    this.streamInterval = null;
    this.autoScroll = true;
    this.searchTerm = '';
    this.logLevel = 'all';
    this.showTimestamp = true;
    this.followLogs = true;
    
    // 性能优化相关
    this.batchSize = 50; // 批处理大小
    this.renderThrottle = null; // 渲染节流
    this.scrollThrottle = null; // 滚动节流
    this.animationFrame = null; // 动画帧
    
    this.modal = null;
    this.logsContainer = null;
    this.statusIndicator = null;
    
    this.init();
  }

  init() {
    this.createModal();
    this.bindEvents();
  }

  // 创建日志查看模态框
  createModal() {
    const modalHtml = `
      <!-- Pod日志查看器模态框 -->
      <div class="modal fade" id="pod-logs-modal" tabindex="-1" data-bs-backdrop="static">
        <div class="modal-dialog modal-fullscreen-lg-down modal-xl">
          <div class="modal-content">
            <div class="modal-header bg-dark text-white">
              <h5 class="modal-title d-flex align-items-center">
                <i class="fas fa-terminal me-2"></i>
                <span id="logs-modal-title">Pod日志</span>
              </h5>
              <div class="header-controls d-flex align-items-center gap-3 me-3">
                <!-- 连接状态指示器 -->
                <div class="status-indicator" id="logs-status-indicator">
                  <span class="status-dot status-disconnected"></span>
                  <small id="logs-status-text">未连接</small>
                </div>
                
                <!-- 快速控制按钮 -->
                <div class="quick-controls d-flex align-items-center gap-2">
                  <button class="btn btn-sm btn-outline-light" id="logs-start-stop-btn" title="开始/停止流式传输">
                    <i class="fas fa-play"></i>
                  </button>
                  <button class="btn btn-sm btn-outline-light" id="logs-clear-btn" title="清空日志">
                    <i class="fas fa-trash"></i>
                  </button>
                  <button class="btn btn-sm btn-outline-light" id="logs-download-btn" title="下载日志">
                    <i class="fas fa-download"></i>
                  </button>
                </div>
              </div>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            
            <div class="modal-body p-0 bg-light">
              <!-- 工具栏 -->
              <div class="logs-toolbar">
                <div class="toolbar-section">
                  <div class="toolbar-left">
                    <!-- 容器选择 -->
                    <div class="control-group">
                      <label>容器:</label>
                      <select class="form-select form-select-sm" id="logs-container-select">
                        <option value="">选择容器...</option>
                      </select>
                    </div>
                    
                    <!-- 日志级别筛选 -->
                    <div class="control-group">
                      <label>级别:</label>
                      <select class="form-select form-select-sm" id="logs-level-filter">
                        <option value="all">全部</option>
                        <option value="error">错误</option>
                        <option value="warn">警告</option>
                        <option value="info">信息</option>
                        <option value="debug">调试</option>
                      </select>
                    </div>
                    
                    <!-- 行数限制 -->
                    <div class="control-group">
                      <label>行数:</label>
                      <select class="form-select form-select-sm" id="logs-lines-limit">
                        <option value="100">100行</option>
                        <option value="500" selected>500行</option>
                        <option value="1000">1000行</option>
                        <option value="5000">5000行</option>
                        <option value="0">全部</option>
                      </select>
                    </div>
                  </div>
                  
                  <div class="toolbar-center">
                    <!-- 搜索框 -->
                    <div class="search-group">
                      <div class="input-group input-group-sm">
                        <input type="text" class="form-control" id="logs-search-input" 
                               placeholder="搜索日志内容...">
                        <button class="btn btn-outline-secondary" type="button" id="logs-search-clear">
                          <i class="fas fa-times"></i>
                        </button>
                      </div>
                    </div>
                  </div>
                  
                  <div class="toolbar-right">
                    <!-- 显示选项 -->
                    <div class="options-group">
                      <div class="form-check form-switch form-check-inline">
                        <input class="form-check-input" type="checkbox" id="logs-show-timestamp" checked>
                        <label class="form-check-label" for="logs-show-timestamp">时间戳</label>
                      </div>
                      <div class="form-check form-switch form-check-inline">
                        <input class="form-check-input" type="checkbox" id="logs-auto-scroll" checked>
                        <label class="form-check-label" for="logs-auto-scroll">自动滚动</label>
                      </div>
                      <div class="form-check form-switch form-check-inline">
                        <input class="form-check-input" type="checkbox" id="logs-follow-mode" checked>
                        <label class="form-check-label" for="logs-follow-mode">实时跟踪</label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 日志显示区域 -->
              <div class="logs-display-container">
                <div class="logs-content" id="pod-logs-content">
                  <div class="logs-placeholder">
                    <i class="fas fa-terminal fa-3x text-muted"></i>
                    <h5 class="text-muted mt-3">Pod日志查看器</h5>
                    <p class="text-muted">选择容器并点击开始按钮来查看实时日志</p>
                  </div>
                </div>
              </div>
              
              <!-- 底部状态栏 -->
              <div class="logs-status-bar">
                <div class="status-left">
                  <span class="log-count">总计: <span id="logs-total-count">0</span> 行</span>
                  <span class="filtered-count">显示: <span id="logs-filtered-count">0</span> 行</span>
                </div>
                <div class="status-center">
                  <span id="logs-streaming-indicator" class="streaming-indicator" style="display: none;">
                    <i class="fas fa-circle text-success blink"></i> 实时传输中...
                  </span>
                </div>
                <div class="status-right">
                  <span class="connection-info" id="logs-connection-info">未连接</span>
                </div>
              </div>
            </div>
            
            <div class="modal-footer bg-light">
              <div class="footer-left">
                <div class="btn-group" role="group">
                  <button type="button" class="btn btn-outline-secondary btn-sm" id="logs-scroll-top">
                    <i class="fas fa-angle-double-up"></i> 顶部
                  </button>
                  <button type="button" class="btn btn-outline-secondary btn-sm" id="logs-scroll-bottom">
                    <i class="fas fa-angle-double-down"></i> 底部
                  </button>
                </div>
              </div>
              <div class="footer-right">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // 插入到页面中
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // 获取元素引用
    this.modal = document.getElementById('pod-logs-modal');
    this.logsContainer = document.getElementById('pod-logs-content');
    this.statusIndicator = document.getElementById('logs-status-indicator');
  }

  // 绑定事件
  bindEvents() {
    // 开始/停止按钮
    document.getElementById('logs-start-stop-btn')?.addEventListener('click', this.toggleStreaming.bind(this));
    
    // 清空日志
    document.getElementById('logs-clear-btn')?.addEventListener('click', this.clearLogs.bind(this));
    
    // 下载日志
    document.getElementById('logs-download-btn')?.addEventListener('click', this.downloadLogs.bind(this));
    
    // 容器选择
    document.getElementById('logs-container-select')?.addEventListener('change', this.handleContainerChange.bind(this));
    
    // 日志级别筛选
    document.getElementById('logs-level-filter')?.addEventListener('change', this.handleLevelFilter.bind(this));
    
    // 行数限制
    document.getElementById('logs-lines-limit')?.addEventListener('change', this.handleLinesLimit.bind(this));
    
    // 搜索
    const searchInput = document.getElementById('logs-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', this.debounce(this.handleSearch.bind(this), 300));
    }
    
    // 搜索清空
    document.getElementById('logs-search-clear')?.addEventListener('click', this.clearSearch.bind(this));
    
    // 显示选项
    document.getElementById('logs-show-timestamp')?.addEventListener('change', this.handleTimestampToggle.bind(this));
    document.getElementById('logs-auto-scroll')?.addEventListener('change', this.handleAutoScrollToggle.bind(this));
    document.getElementById('logs-follow-mode')?.addEventListener('change', this.handleFollowModeToggle.bind(this));
    
    // 滚动控制
    document.getElementById('logs-scroll-top')?.addEventListener('click', this.scrollToTop.bind(this));
    document.getElementById('logs-scroll-bottom')?.addEventListener('click', this.scrollToBottom.bind(this));
    
    // 模态框事件
    if (this.modal) {
      this.modal.addEventListener('hidden.bs.modal', this.handleModalClose.bind(this));
    }
    
    // 键盘快捷键
    document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
  }

  // 显示Pod日志
  async showLogs(cluster, namespace, podName, container = null) {
    this.currentCluster = cluster;
    this.currentNamespace = namespace;
    this.currentPod = podName;
    this.currentContainer = container;
    
    // 更新模态框标题
    const title = document.getElementById('logs-modal-title');
    if (title) {
      title.textContent = `${podName} - 日志查看器`;
    }
    
    // 清空日志显示
    this.clearLogs();
    
    // 加载容器列表
    await this.loadContainers();
    
    // 如果指定了容器，选中它
    if (container) {
      const containerSelect = document.getElementById('logs-container-select');
      if (containerSelect) {
        containerSelect.value = container;
      }
    }
    
    // 显示模态框
    const modal = new bootstrap.Modal(this.modal);
    modal.show();
    
    // 自动开始流式传输（如果有容器）
    if (this.currentContainer || this.getSelectedContainer()) {
      setTimeout(() => {
        this.startStreaming();
      }, 500);
    }
  }

  // 加载容器列表
  async loadContainers() {
    try {
      const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${this.currentNamespace}/pods/${this.currentPod}`);
      const data = await response.json();
      
      if (data.success && data.data && data.data.containers) {
        const select = document.getElementById('logs-container-select');
        if (select) {
          select.innerHTML = '<option value="">选择容器...</option>';
          data.data.containers.forEach(container => {
            const option = document.createElement('option');
            option.value = container.name;
            option.textContent = `${container.name} (${container.image})`;
            select.appendChild(option);
          });
          
          // 如果只有一个容器，自动选中
          if (data.data.containers.length === 1) {
            select.value = data.data.containers[0].name;
            this.currentContainer = data.data.containers[0].name;
          }
        }
      }
    } catch (error) {
      console.error('Failed to load containers:', error);
      this.showError('加载容器列表失败: ' + error.message);
    }
  }

  // 开始流式传输日志
  async startStreaming() {
    const container = this.getSelectedContainer();
    if (!container) {
      this.showError('请先选择一个容器');
      return;
    }

    if (this.isStreaming) {
      return;
    }

    this.isStreaming = true;
    this.updateUI();
    
    // 移除占位符
    this.removePlaceholder();
    
    try {
      // 获取行数限制
      const linesLimit = document.getElementById('logs-lines-limit')?.value || '500';
      const lines = linesLimit === '0' ? null : parseInt(linesLimit);
      
      // 首次加载历史日志
      await this.fetchInitialLogs(container, lines);
      
      // 如果开启了实时跟踪，启动轮询
      if (this.followLogs) {
        this.startPolling(container);
      }
      
      this.updateStatusIndicator('connected', '已连接');
      
    } catch (error) {
      console.error('Failed to start streaming:', error);
      this.showError('启动日志流失败: ' + error.message);
      this.stopStreaming();
    }
  }

  // 停止流式传输
  stopStreaming() {
    this.isStreaming = false;
    this.stopPolling();
    this.updateUI();
    this.updateStatusIndicator('disconnected', '已断开');
  }

  // 切换流式传输状态
  toggleStreaming() {
    if (this.isStreaming) {
      this.stopStreaming();
    } else {
      this.startStreaming();
    }
  }

  // 获取初始日志
  async fetchInitialLogs(container, lines) {
    const params = new URLSearchParams({
      container: container,
      follow: 'false',
      timestamps: 'true'
    });
    
    if (lines) {
      params.append('tailLines', lines.toString());
    }
    
    const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${this.currentNamespace}/pods/${this.currentPod}/logs?${params}`);
    const data = await response.json();
    
    if (data.success && data.data) {
      const logs = data.data.split('\n').filter(line => line.trim());
      this.logBuffer = logs;
      this.displayLogs();
    } else {
      throw new Error(data.message || '获取日志失败');
    }
  }

  // 启动轮询获取新日志 - 优化版本
  startPolling(container) {
    this.stopPolling();
    
    // 自适应轮询间隔：有新日志时更频繁，无新日志时降低频率
    let pollInterval = 1000; // 初始1秒
    let consecutiveEmptyPolls = 0;
    
    const poll = async () => {
      try {
        const hadNewLogs = await this.fetchNewLogs(container);
        
        if (hadNewLogs) {
          consecutiveEmptyPolls = 0;
          pollInterval = 1000; // 有新日志时保持1秒轮询
        } else {
          consecutiveEmptyPolls++;
          // 逐渐降低轮询频率，最多到5秒
          pollInterval = Math.min(1000 + consecutiveEmptyPolls * 500, 5000);
        }
        
        // 设置下一次轮询
        this.streamInterval = setTimeout(poll, pollInterval);
        
      } catch (error) {
        console.error('Polling error:', error);
        // 出错时等待2秒后重试
        this.streamInterval = setTimeout(poll, 2000);
      }
    };
    
    // 开始轮询
    this.streamInterval = setTimeout(poll, pollInterval);
  }

  // 停止轮询
  stopPolling() {
    if (this.streamInterval) {
      clearInterval(this.streamInterval);
      this.streamInterval = null;
    }
  }

  // 获取新日志 - 优化版本
  async fetchNewLogs(container) {
    // 获取最后一条日志的时间戳作为since参数
    const lastTimestamp = this.getLastLogTimestamp();
    
    const params = new URLSearchParams({
      container: container,
      follow: 'false',
      timestamps: 'true'
    });
    
    if (lastTimestamp) {
      params.append('sinceTime', lastTimestamp);
    }
    
    const response = await fetch(`/api/k8s/clusters/${this.currentCluster}/namespaces/${this.currentNamespace}/pods/${this.currentPod}/logs?${params}`);
    const data = await response.json();
    
    if (data.success && data.data) {
      const newLogs = data.data.split('\n').filter(line => line.trim());
      if (newLogs.length > 0) {
        this.appendLogs(newLogs);
        return true; // 返回true表示有新日志
      }
    }
    
    return false; // 返回false表示没有新日志
  }

  // 显示日志 - 优化版本
  displayLogs() {
    // 取消之前的渲染任务
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    
    const filteredLogs = this.filterLogs(this.logBuffer);
    
    // 清空容器
    this.logsContainer.innerHTML = '';
    
    // 如果日志数量较少，直接渲染
    if (filteredLogs.length <= this.batchSize) {
      const fragment = document.createDocumentFragment();
      filteredLogs.forEach(line => {
        const logElement = this.createLogElement(line);
        if (logElement) {
          fragment.appendChild(logElement);
        }
      });
      this.logsContainer.appendChild(fragment);
      this.updateLogCounts();
      
      if (this.autoScroll) {
        this.smoothScrollToBottom();
      }
    } else {
      // 使用批量渲染
      this.batchRenderLogs(filteredLogs);
    }
  }

  // 追加新日志 - 优化版本
  appendLogs(newLogs) {
    if (newLogs.length === 0) return;
    
    // 记录当前滚动状态
    const wasAtBottom = this.isScrollAtBottom();
    const shouldAutoScroll = this.autoScroll && wasAtBottom;
    
    // 使用DocumentFragment来提高DOM操作性能
    const fragment = document.createDocumentFragment();
    const newLogElements = [];
    
    newLogs.forEach(line => {
      this.logBuffer.push(line);
      
      // 检查过滤条件
      if (this.shouldShowLog(line)) {
        const logElement = this.createLogElement(line);
        if (logElement) {
          fragment.appendChild(logElement);
          newLogElements.push(logElement);
        }
      }
    });
    
    // 检查缓冲区大小限制
    if (this.logBuffer.length > this.maxBufferSize) {
      this.logBuffer = this.logBuffer.slice(-this.maxBufferSize + 1000);
      // 重新显示所有日志以保持一致性
      this.displayLogs();
      return;
    }
    
    // 一次性添加所有新的日志元素
    if (fragment.childElementCount > 0) {
      this.logsContainer.appendChild(fragment);
      
      // 如果启用了动画效果，为新日志添加淡入效果
      if (newLogElements.length > 0) {
        this.animateNewLogs(newLogElements);
      }
    }
    
    this.updateLogCounts();
    
    // 平滑滚动到底部
    if (shouldAutoScroll) {
      this.smoothScrollToBottom();
    }
  }

  // 检查是否滚动到底部
  isScrollAtBottom() {
    const container = this.logsContainer;
    const threshold = 50; // 50px的容差范围
    return (container.scrollTop + container.clientHeight) >= (container.scrollHeight - threshold);
  }

  // 创建单个日志元素 - 优化版本
  createLogElement(logLine) {
    const { timestamp, level, content } = this.parseLogLine(logLine);
    
    const logElement = document.createElement('div');
    logElement.className = 'log-line';
    
    // 使用innerHTML比多次DOM操作更高效
    let html = '';
    
    // 时间戳
    if (this.showTimestamp && timestamp) {
      html += `<span class="log-timestamp">${this.formatTimestamp(timestamp)}</span>`;
    }
    
    // 日志级别
    if (level) {
      html += `<span class="log-level log-level-${level.toLowerCase()}">${level}</span>`;
      logElement.classList.add(`log-line-${level.toLowerCase()}`);
    }
    
    // 日志内容
    html += `<span class="log-content">${this.escapeHtml(content)}</span>`;
    
    logElement.innerHTML = html;
    
    // 高亮搜索词
    if (this.searchTerm) {
      this.highlightSearchTerm(logElement);
    }
    
    return logElement;
  }

  // 为新日志添加淡入动画 - 优化版本
  animateNewLogs(elements) {
    if (!elements.length) return;
    
    // 使用CSS类而不是内联样式以提高性能
    elements.forEach((element, index) => {
      element.classList.add('log-line-entering');
      
      // 如果是实时流，添加流动画效果
      if (this.isStreaming && this.followLogs) {
        element.classList.add('log-line-streaming');
        // 3秒后移除流动画效果
        setTimeout(() => {
          element.classList.remove('log-line-streaming');
        }, 3000);
      }
      
      // 错开动画时间，创造波浪效果
      setTimeout(() => {
        element.classList.remove('log-line-entering');
      }, 300 + index * 10); // 减少延迟以提高响应速度
    });
  }

  // 平滑滚动到底部 - 优化版本
  smoothScrollToBottom() {
    // 取消之前的滚动动画
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    
    const container = this.logsContainer;
    const targetScrollTop = container.scrollHeight - container.clientHeight;
    const currentScrollTop = container.scrollTop;
    
    // 如果已经在底部附近，直接跳转
    if (Math.abs(targetScrollTop - currentScrollTop) < 10) {
      container.scrollTop = targetScrollTop;
      return;
    }
    
    // 使用节流的滚动动画
    if (this.scrollThrottle) {
      clearTimeout(this.scrollThrottle);
    }
    
    this.scrollThrottle = setTimeout(() => {
      this.performSmoothScroll(container, currentScrollTop, targetScrollTop);
    }, 16); // 约60fps
  }

  // 执行平滑滚动
  performSmoothScroll(container, start, target) {
    const duration = 250; // 减少动画时长以提高响应速度
    const startTime = performance.now();
    
    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // 使用easeOutQuart缓动函数，更流畅的效果
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      
      const current = start + (target - start) * easeOutQuart;
      container.scrollTop = current;
      
      if (progress < 1) {
        this.animationFrame = requestAnimationFrame(animate);
      } else {
        this.animationFrame = null;
      }
    };
    
    this.animationFrame = requestAnimationFrame(animate);
  }

  // 批量处理日志显示 - 新增优化方法
  batchRenderLogs(logs) {
    if (!logs.length) return;
    
    const fragment = document.createDocumentFragment();
    const batchSize = this.batchSize;
    let batchIndex = 0;
    
    const renderBatch = () => {
      const startIndex = batchIndex * batchSize;
      const endIndex = Math.min(startIndex + batchSize, logs.length);
      
      for (let i = startIndex; i < endIndex; i++) {
        const logElement = this.createLogElement(logs[i]);
        if (logElement) {
          fragment.appendChild(logElement);
        }
      }
      
      batchIndex++;
      
      if (endIndex < logs.length) {
        // 继续下一批
        this.animationFrame = requestAnimationFrame(renderBatch);
      } else {
        // 完成所有渲染
        this.logsContainer.appendChild(fragment);
        this.updateLogCounts();
        
        if (this.autoScroll) {
          this.smoothScrollToBottom();
        }
      }
    };
    
    // 开始批量渲染
    this.animationFrame = requestAnimationFrame(renderBatch);
  }

  // 添加单行日志
  appendLogLine(logLine) {
    const logElement = document.createElement('div');
    logElement.className = 'log-line';
    
    const { timestamp, level, content } = this.parseLogLine(logLine);
    
    let html = '';
    
    // 时间戳
    if (this.showTimestamp && timestamp) {
      html += `<span class="log-timestamp">${this.formatTimestamp(timestamp)}</span>`;
    }
    
    // 日志级别
    if (level) {
      html += `<span class="log-level log-level-${level.toLowerCase()}">${level}</span>`;
    }
    
    // 日志内容
    html += `<span class="log-content">${this.escapeHtml(content)}</span>`;
    
    logElement.innerHTML = html;
    
    // 添加日志级别样式
    if (level) {
      logElement.classList.add(`log-line-${level.toLowerCase()}`);
    }
    
    // 高亮搜索词
    if (this.searchTerm) {
      this.highlightSearchTerm(logElement);
    }
    
    this.logsContainer.appendChild(logElement);
  }

  // 过滤日志
  filterLogs(logs) {
    return logs.filter(line => this.shouldShowLog(line));
  }

  // 判断是否应该显示日志行
  shouldShowLog(logLine) {
    const { level, content } = this.parseLogLine(logLine);
    
    // 日志级别过滤
    if (this.logLevel !== 'all' && level && level.toLowerCase() !== this.logLevel) {
      return false;
    }
    
    // 搜索过滤
    if (this.searchTerm && !content.toLowerCase().includes(this.searchTerm.toLowerCase())) {
      return false;
    }
    
    return true;
  }

  // 解析日志行
  parseLogLine(logLine) {
    let timestamp = null;
    let level = null;
    let content = logLine;
    
    // 提取时间戳 (RFC3339格式)
    const timestampMatch = logLine.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z?)\s+(.*)$/);
    if (timestampMatch) {
      timestamp = timestampMatch[1];
      content = timestampMatch[2];
    }
    
    // 提取日志级别
    const levelMatch = content.match(/^\[?(ERROR|WARN|INFO|DEBUG)\]?\s*(.*)$/i);
    if (levelMatch) {
      level = levelMatch[1].toUpperCase();
      content = levelMatch[2];
    }
    
    return { timestamp, level, content };
  }

  // 格式化时间戳
  formatTimestamp(timestamp) {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('zh-CN', { 
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
      });
    } catch (error) {
      return timestamp;
    }
  }

  // HTML转义
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // 高亮搜索词
  highlightSearchTerm(element) {
    if (!this.searchTerm) return;
    
    const content = element.querySelector('.log-content');
    if (!content) return;
    
    const text = content.textContent;
    const regex = new RegExp(`(${this.escapeRegExp(this.searchTerm)})`, 'gi');
    const highlighted = text.replace(regex, '<mark>$1</mark>');
    content.innerHTML = highlighted;
  }

  // 转义正则表达式特殊字符
  escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // 获取选中的容器
  getSelectedContainer() {
    const select = document.getElementById('logs-container-select');
    return select?.value || this.currentContainer;
  }

  // 获取最后一条日志的时间戳
  getLastLogTimestamp() {
    if (this.logBuffer.length === 0) return null;
    
    const lastLog = this.logBuffer[this.logBuffer.length - 1];
    const { timestamp } = this.parseLogLine(lastLog);
    return timestamp;
  }

  // 事件处理函数
  handleContainerChange(event) {
    this.currentContainer = event.target.value;
    if (this.isStreaming) {
      this.stopStreaming();
      if (this.currentContainer) {
        setTimeout(() => this.startStreaming(), 100);
      }
    }
  }

  handleLevelFilter(event) {
    this.logLevel = event.target.value;
    this.displayLogs();
  }

  handleLinesLimit(event) {
    // 重新开始流式传输以应用新的行数限制
    if (this.isStreaming) {
      this.stopStreaming();
      setTimeout(() => this.startStreaming(), 100);
    }
  }

  handleSearch(event) {
    this.searchTerm = event.target.value;
    this.displayLogs();
  }

  clearSearch() {
    const searchInput = document.getElementById('logs-search-input');
    if (searchInput) {
      searchInput.value = '';
      this.searchTerm = '';
      this.displayLogs();
    }
  }

  handleTimestampToggle(event) {
    this.showTimestamp = event.target.checked;
    this.displayLogs();
  }

  handleAutoScrollToggle(event) {
    this.autoScroll = event.target.checked;
    if (this.autoScroll) {
      this.scrollToBottom();
    }
  }

  handleFollowModeToggle(event) {
    this.followLogs = event.target.checked;
    if (this.isStreaming) {
      if (this.followLogs) {
        this.startPolling(this.getSelectedContainer());
      } else {
        this.stopPolling();
      }
    }
  }

  handleModalClose() {
    this.stopStreaming();
    this.cleanup();
  }

  // 清理资源
  cleanup() {
    // 清理动画帧
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    
    // 清理定时器
    if (this.renderThrottle) {
      clearTimeout(this.renderThrottle);
      this.renderThrottle = null;
    }
    
    if (this.scrollThrottle) {
      clearTimeout(this.scrollThrottle);
      this.scrollThrottle = null;
    }
    
    // 移除动画类
    const logLines = this.logsContainer?.querySelectorAll('.log-line');
    if (logLines) {
      logLines.forEach(line => {
        line.classList.remove('log-line-entering', 'log-line-streaming');
      });
    }
  }

  handleKeyboardShortcuts(event) {
    // 只在模态框打开时处理快捷键
    if (!this.modal || !this.modal.classList.contains('show')) {
      return;
    }
    
    // Ctrl/Cmd + F: 聚焦搜索框
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
      event.preventDefault();
      const searchInput = document.getElementById('logs-search-input');
      if (searchInput) searchInput.focus();
    }
    
    // 空格键: 暂停/恢复自动滚动
    if (event.key === ' ' && event.target.tagName !== 'INPUT') {
      event.preventDefault();
      this.autoScroll = !this.autoScroll;
      const autoScrollCheckbox = document.getElementById('logs-auto-scroll');
      if (autoScrollCheckbox) autoScrollCheckbox.checked = this.autoScroll;
    }
    
    // Home: 滚动到顶部
    if (event.key === 'Home') {
      event.preventDefault();
      this.scrollToTop();
    }
    
    // End: 滚动到底部
    if (event.key === 'End') {
      event.preventDefault();
      this.scrollToBottom();
    }
  }

  // UI更新函数
  updateUI() {
    const startStopBtn = document.getElementById('logs-start-stop-btn');
    if (startStopBtn) {
      const icon = startStopBtn.querySelector('i');
      if (this.isStreaming) {
        icon.className = 'fas fa-stop';
        startStopBtn.title = '停止流式传输';
        startStopBtn.classList.remove('btn-outline-light');
        startStopBtn.classList.add('btn-outline-danger');
      } else {
        icon.className = 'fas fa-play';
        startStopBtn.title = '开始流式传输';
        startStopBtn.classList.remove('btn-outline-danger');
        startStopBtn.classList.add('btn-outline-light');
      }
    }
    
    const streamingIndicator = document.getElementById('logs-streaming-indicator');
    if (streamingIndicator) {
      streamingIndicator.style.display = this.isStreaming ? 'inline-flex' : 'none';
    }
  }

  updateStatusIndicator(status, text) {
    const indicator = document.getElementById('logs-status-indicator');
    const statusText = document.getElementById('logs-status-text');
    const connectionInfo = document.getElementById('logs-connection-info');
    
    if (indicator) {
      const dot = indicator.querySelector('.status-dot');
      dot.className = `status-dot status-${status}`;
    }
    
    if (statusText) {
      statusText.textContent = text;
    }
    
    if (connectionInfo) {
      connectionInfo.textContent = text;
    }
  }

  updateLogCounts() {
    const totalCount = document.getElementById('logs-total-count');
    const filteredCount = document.getElementById('logs-filtered-count');
    
    if (totalCount) {
      totalCount.textContent = this.logBuffer.length;
    }
    
    if (filteredCount) {
      const visible = this.logsContainer.querySelectorAll('.log-line').length;
      filteredCount.textContent = visible;
    }
  }

  // 滚动控制
  scrollToTop() {
    this.logsContainer.scrollTop = 0;
  }

  scrollToBottom() {
    this.logsContainer.scrollTop = this.logsContainer.scrollHeight;
  }

  // 工具函数
  clearLogs() {
    this.logBuffer = [];
    this.logsContainer.innerHTML = '<div class="logs-placeholder"><i class="fas fa-terminal fa-3x text-muted"></i><h5 class="text-muted mt-3">准备加载日志...</h5></div>';
    this.updateLogCounts();
  }

  removePlaceholder() {
    const placeholder = this.logsContainer.querySelector('.logs-placeholder');
    if (placeholder) {
      placeholder.remove();
    }
  }

  async downloadLogs() {
    if (this.logBuffer.length === 0) {
      this.showError('没有可下载的日志');
      return;
    }
    
    const logContent = this.logBuffer.join('\n');
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `${this.currentPod}_${this.getSelectedContainer()}_${timestamp}.log`;
    
    const blob = new Blob([logContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    this.showNotification('日志文件下载成功', 'success');
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

  // 通知函数
  showNotification(message, type = 'info') {
    if (window.showNotification && typeof window.showNotification === 'function') {
      window.showNotification(message, type);
    } else {
      console.log(`${type.toUpperCase()}: ${message}`);
    }
  }

  showError(message) {
    this.showNotification(message, 'error');
  }
}

// 全局实例
let podLogsViewer;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  podLogsViewer = new PodLogsViewer();
});

// 导出给全局使用
if (typeof window !== 'undefined') {
  window.PodLogsViewer = PodLogsViewer;
  window.showPodLogs = function(cluster, namespace, podName, container) {
    if (podLogsViewer) {
      podLogsViewer.showLogs(cluster, namespace, podName, container);
    }
  };
}

console.log('🔍 Pod日志查看器组件加载完成');