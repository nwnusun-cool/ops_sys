// Pod终端管理器 - 使用xterm.js和Socket.IO
console.log('🔌 pod-terminal.js 加载成功');

class PodTerminalManager {
  constructor() {
    this.socket = null;
    this.terminal = null;
    this.currentSession = null;
    this.isConnected = false;
    this.modal = null;
    
    this.init();
  }
  
  init() {
    this.modal = document.getElementById('pod-terminal-modal');
    this.bindEvents();
  }
  
  bindEvents() {
    // 模态框关闭事件
    const modal = this.modal;
    if (modal) {
      modal.addEventListener('hidden.bs.modal', () => {
        this.disconnect(true); // 完全断开
      });
    }
    
    // 容器切换事件
    const containerSelect = document.getElementById('terminal-container-select');
    if (containerSelect) {
      containerSelect.addEventListener('change', this.handleContainerChange.bind(this));
    }
    
    // 重连按钮
    const reconnectBtn = document.getElementById('terminal-reconnect-btn');
    if (reconnectBtn) {
      reconnectBtn.addEventListener('click', this.reconnect.bind(this));
    }
    
    // 清屏按钮
    const clearBtn = document.getElementById('terminal-clear-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', this.clearTerminal.bind(this));
    }
    
    // 断开连接按钮
    const disconnectBtn = document.getElementById('terminal-disconnect-btn');
    if (disconnectBtn) {
      disconnectBtn.addEventListener('click', () => this.disconnect(true));
    }
  }
  
  async showTerminal(clusterId, namespace, podName, container = null) {
    console.log('🖥️ 打开终端:', clusterId, namespace, podName, container);
    
    try {
      // 保存会话信息
      this.currentSession = {
        clusterId,
        namespace, 
        podName,
        container
      };
      
      // 获取Pod容器列表
      await this.loadContainers(clusterId, namespace, podName);
      
      // 更新模态框标题
      this.updateModalTitle(namespace, podName);
      
      // 显示模态框
      this.showModal();
      
      // 初始化终端
      this.initTerminal();
      
      // 连接到Pod
      this.connect();
      
    } catch (error) {
      console.error('打开终端失败:', error);
      this.showError('打开终端失败: ' + error.message);
    }
  }
  
  async loadContainers(clusterId, namespace, podName) {
    try {
      const response = await fetch(`/api/k8s/clusters/${clusterId}/namespaces/${namespace}/pods/${podName}/exec/containers`);
      const data = await response.json();
      
      if (data.success) {
        this.populateContainerSelect(data.data);
        
        // 如果没有指定容器，使用第一个
        if (!this.currentSession.container && data.data.length > 0) {
          this.currentSession.container = data.data[0].name;
        }
      } else {
        throw new Error(data.error || '获取容器列表失败');
      }
    } catch (error) {
      console.error('获取容器列表失败:', error);
      throw error;
    }
  }
  
  populateContainerSelect(containers) {
    const select = document.getElementById('terminal-container-select');
    if (!select) return;
    
    select.innerHTML = '';
    
    containers.forEach(container => {
      const option = document.createElement('option');
      option.value = container.name;
      option.textContent = `${container.name} (${this.getShortImageName(container.image)})`;
      
      // 选中当前容器
      if (container.name === this.currentSession.container) {
        option.selected = true;
      }
      
      select.appendChild(option);
    });
  }
  
  getShortImageName(imageName) {
    // 提取镜像名称的简短形式
    if (!imageName) return 'unknown';
    
    const parts = imageName.split('/');
    const nameTag = parts[parts.length - 1];
    const [name] = nameTag.split(':');
    
    return name;
  }
  
  updateModalTitle(namespace, podName) {
    const titleElement = document.getElementById('terminal-modal-title');
    if (titleElement) {
      titleElement.innerHTML = `
        <i class="fas fa-terminal"></i>
        ${namespace}/${podName} - 终端
      `;
    }
  }
  
  showModal() {
    if (this.modal) {
      if (window.bootstrap && bootstrap.Modal) {
        const bsModal = new bootstrap.Modal(this.modal);
        bsModal.show();
      } else if (window.$ && $.fn.modal) {
        $(this.modal).modal('show');
      }
    }
  }
  
  initTerminal() {
    // 如果xterm.js未加载，显示错误
    if (typeof Terminal === 'undefined') {
      this.showError('终端组件未加载，请确认xterm.js已正确引入');
      return;
    }
    
    // 清理现有终端
    if (this.terminal) {
      this.terminal.dispose();
      this.terminal = null;
    }
    
    // 创建新终端
    this.terminal = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontSize: 14,
      fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      theme: {
        background: '#1a202c',
        foreground: '#e2e8f0',
        cursor: '#63b3ed',
        selection: 'rgba(255, 255, 255, 0.3)',
        black: '#2d3748',
        red: '#f56565',
        green: '#48bb78',
        yellow: '#ed8936',
        blue: '#4299e1',
        magenta: '#9f7aea',
        cyan: '#38b2ac',
        white: '#e2e8f0',
        brightBlack: '#4a5568',
        brightRed: '#fc8181',
        brightGreen: '#68d391',
        brightYellow: '#f6e05e',
        brightBlue: '#63b3ed',
        brightMagenta: '#b794f6',
        brightCyan: '#4fd1c7',
        brightWhite: '#f7fafc'
      },
      cols: 80,
      rows: 24,
      convertEol: true,
      disableStdin: false
    });
    
    // 挂载终端到DOM
    const container = document.getElementById('terminal-container');
    if (container) {
      container.innerHTML = ''; // 清空容器
      this.terminal.open(container);
      
      // 调整大小适配容器
      this.fitTerminal();
      
      // 监听窗口大小变化
      window.addEventListener('resize', this.fitTerminal.bind(this));
    }
    
    // 监听用户输入
    this.terminal.onData(data => {
      if (this.socket && this.isConnected) {
        this.socket.emit('pod_terminal_input', { data });
      }
    });
    
    // 监听终端大小变化
    this.terminal.onResize(size => {
      if (this.socket && this.isConnected) {
        this.socket.emit('pod_terminal_resize', {
          cols: size.cols,
          rows: size.rows
        });
      }
    });
  }
  
  fitTerminal() {
    if (this.terminal && this.terminal.element) {
      // 使用xterm-addon-fit如果可用
      if (typeof FitAddon !== 'undefined') {
        if (!this.fitAddon) {
          this.fitAddon = new FitAddon.FitAddon();
          this.terminal.loadAddon(this.fitAddon);
        }
        this.fitAddon.fit();
      } else {
        // 手动计算大小
        const container = this.terminal.element.parentElement;
        if (container) {
          const rect = container.getBoundingClientRect();
          const cols = Math.floor(rect.width / 9.6); // 近似字符宽度
          const rows = Math.floor(rect.height / 17); // 近似行高
          
          if (cols > 10 && rows > 5) {
            this.terminal.resize(Math.max(cols, 20), Math.max(rows, 10));
          }
        }
      }
    }
  }
  
  connect() {
    console.log('🔌 连接到Pod终端...');
    
    // 显示连接状态
    this.updateStatus('connecting', '连接中...');
    this.showOverlay('连接到容器中...');
    
    // 如果Socket.IO未加载，显示错误
    if (typeof io === 'undefined') {
      this.showError('WebSocket组件未加载，请确认socket.io已正确引入');
      return;
    }
    
    try {
      // 创建WebSocket连接
      this.socket = io();
      
      // 监听连接事件
      this.socket.on('connect', () => {
        console.log('✅ WebSocket连接成功');
        
        // 发送终端连接请求
        const connectData = {
          cluster_id: this.currentSession.clusterId,
          namespace: this.currentSession.namespace,
          pod_name: this.currentSession.podName,
          container: this.currentSession.container
        };
        console.log('📤 发送终端连接请求:', connectData);
        this.socket.emit('pod_terminal_connect', connectData);
      });
      
      // 监听终端连接成功
      this.socket.on('pod_terminal_connected', (data) => {
        console.log('🖥️ 终端连接成功:', data);
        this.isConnected = true;
        this.updateStatus('connected', '已连接');
        this.hideOverlay();
        
        // 聚焦终端并显示欢迎信息
        if (this.terminal) {
          this.terminal.writeln('\r\n\x1b[32m[终端连接成功]\x1b[0m\r\n');
          this.terminal.focus();
        }
      });
      
      // 监听终端输出
      this.socket.on('pod_terminal_output', (data) => {
        if (this.terminal && data.data) {
          this.terminal.write(data.data);
        }
      });
      
      // 监听终端错误
      this.socket.on('pod_terminal_error', (data) => {
        console.error('终端错误:', data.error);
        this.showError(data.error);
        this.updateStatus('error', '连接错误');
      });
      
      // 监听连接断开
      this.socket.on('disconnect', () => {
        console.log('🔌 WebSocket连接断开');
        this.isConnected = false;
        this.updateStatus('disconnected', '连接断开');
        
        if (this.terminal) {
          this.terminal.writeln('\\r\\n\\x1b[31m[连接已断开]\\x1b[0m\\r\\n');
        }
      });
      
      // 监听连接错误
      this.socket.on('connect_error', (error) => {
        console.error('WebSocket连接错误:', error);
        this.showError('WebSocket连接失败: ' + error.message);
        this.updateStatus('error', '连接失败');
      });
      
    } catch (error) {
      console.error('连接失败:', error);
      this.showError('连接失败: ' + error.message);
      this.updateStatus('error', '连接失败');
    }
  }
  
  disconnect(fullDisconnect = false) {
    console.log('🔌 断开终端连接', fullDisconnect ? '(完全断开)' : '(保留会话)');
    
    this.isConnected = false;
    
    // 断开WebSocket
    if (this.socket) {
      this.socket.emit('pod_terminal_disconnect');
      this.socket.disconnect();
      this.socket = null;
    }
    
    // 清理终端
    if (this.terminal) {
      this.terminal.dispose();
      this.terminal = null;
    }
    
    // 只有完全断开时才清理会话
    if (fullDisconnect) {
      this.currentSession = null;
    }
    
    // 更新状态
    this.updateStatus('disconnected', '已断开');
    
    // 移除窗口大小监听
    window.removeEventListener('resize', this.fitTerminal.bind(this));
  }
  
  reconnect() {
    if (!this.currentSession) {
      this.showError('无会话信息，无法重连');
      return;
    }
    
    console.log('🔄 重新连接终端...');
    
    // 断开当前连接
    this.disconnect();
    
    // 等待一下再重连
    setTimeout(() => {
      this.initTerminal();
      this.connect();
    }, 1000);
  }
  
  clearTerminal() {
    if (this.terminal) {
      this.terminal.clear();
    }
  }
  
  handleContainerChange(event) {
    const newContainer = event.target.value;
    
    if (!this.currentSession || newContainer === this.currentSession.container) {
      return;
    }
    
    console.log('📦 切换容器:', newContainer);
    
    // 更新会话信息
    this.currentSession.container = newContainer;
    
    // 重新连接到新容器
    this.reconnect();
  }
  
  updateStatus(status, message) {
    const statusElement = document.getElementById('terminal-status');
    if (statusElement) {
      statusElement.className = `terminal-status ${status}`;
      statusElement.textContent = message;
    }
  }
  
  showOverlay(message) {
    const overlay = document.getElementById('terminal-overlay');
    if (overlay) {
      overlay.innerHTML = `
        <div class="spinner"></div>
        <span>${message}</span>
      `;
      overlay.classList.remove('hidden');
    }
  }
  
  hideOverlay() {
    const overlay = document.getElementById('terminal-overlay');
    if (overlay) {
      overlay.classList.add('hidden');
    }
  }
  
  showError(message) {
    console.error('终端错误:', message);
    
    // 显示错误覆盖层
    const overlay = document.getElementById('terminal-overlay');
    if (overlay) {
      overlay.innerHTML = `
        <div style="text-align: center;">
          <i class="fas fa-exclamation-triangle fa-2x text-danger mb-3"></i>
          <div class="text-danger">${message}</div>
          <button class="btn btn-outline-light btn-sm mt-3" onclick="podTerminal.reconnect()">
            <i class="fas fa-redo"></i> 重试
          </button>
        </div>
      `;
      overlay.classList.remove('hidden');
    }
    
    // 在终端中显示错误
    if (this.terminal) {
      this.terminal.writeln(`\\r\\n\\x1b[31m[错误] ${message}\\x1b[0m\\r\\n`);
    }
  }
  
  // 工具方法
  static showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      ${message}
      <button type=\"button\" class=\"btn-close\" data-bs-dismiss=\"alert\"></button>
    `;
    
    document.body.appendChild(notification);
    
    // 自动移除
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, type === 'error' ? 8000 : 5000);
  }
}

// 创建全局实例
let podTerminal;
document.addEventListener('DOMContentLoaded', () => {
  podTerminal = new PodTerminalManager();
});

// 全局函数供HTML调用
if (typeof window !== 'undefined') {
  window.showPodTerminal = (clusterId, namespace, podName, container = null) => {
    if (podTerminal) {
      podTerminal.showTerminal(clusterId, namespace, podName, container);
    } else {
      console.error('Pod终端管理器未初始化');
    }
  };
}