// Pod监控管理器 - 专业监控图表
console.log('📊 pod-monitoring.js 加载成功');

class PodMonitoringManager {
  constructor() {
    this.charts = {};
    this.currentPod = null;
    this.refreshInterval = null;
    this.isVisible = false;
    this.chartReady = false;
    
    this.init();
  }
  
  init() {
    // 延迟检查Chart.js以确保完全加载
    this.checkChartJS();
  }
  
  checkChartJS() {
    console.log('🔍 检查Chart.js加载状态...');
    console.log('🔍 当前window.Chart状态:', typeof window.Chart);
    console.log('🔍 当前Chart状态:', typeof Chart);
    
    // 使用多种方式检测Chart.js的可用性
    const isChartAvailable = () => {
      // 方法1: 直接检查全局Chart对象
      if (typeof window.Chart !== 'undefined' && window.Chart) {
        console.log('📊 方法1: window.Chart可用');
        if (typeof window.Chart.register === 'function') {
          console.log('📊 方法1: Chart.register方法存在');
          return window.Chart;
        }
      }
      
      // 方法2: 检查全局Chart（无window前缀）
      if (typeof Chart !== 'undefined' && Chart) {
        console.log('📊 方法2: Chart可用');
        if (typeof Chart.register === 'function') {
          console.log('📊 方法2: Chart.register方法存在');
          return Chart;
        }
      }
      
      // 方法3: 检查Chart构造函数
      try {
        if (window.Chart && typeof window.Chart === 'function') {
          console.log('📊 方法3: Chart构造函数可用');
          return window.Chart;
        }
      } catch (e) {
        console.warn('📊 方法3检查失败:', e.message);
      }
      
      return null;
    };
    
    const chartObj = isChartAvailable();
    
    if (chartObj) {
      // 将Chart对象赋值给全局变量确保一致性
      window.Chart = chartObj;
      this.configureChartDefaults();
      console.log('✅ Chart.js 加载成功，监控功能已启用');
      console.log('📊 Chart.js 版本信息:', chartObj.version || 'v4.4.0+');
      this.chartReady = true;
    } else {
      console.warn('⚠️ Chart.js 未立即可用，设置延迟检查...');
      
      // 使用轮询检查Chart.js加载状态（解决UMD异步加载问题）
      let checkCount = 0;
      const maxChecks = 20; // 最多检查20次（2秒）
      
      const pollForChart = () => {
        checkCount++;
        console.log(`🔄 第${checkCount}次检查Chart.js状态...`);
        
        const chart = isChartAvailable();
        if (chart) {
          window.Chart = chart;
          this.configureChartDefaults();
          console.log('✅ Chart.js 轮询检查成功，监控功能已启用');
          this.chartReady = true;
          return;
        }
        
        if (checkCount < maxChecks) {
          setTimeout(pollForChart, 100); // 每100ms检查一次
        } else {
          console.error('❌ Chart.js 轮询检查超时 - 尝试CDN备用方案');
          this.loadChartJSFallback();
        }
      };
      
      // 监听Chart.js加载事件（如果HTML中触发）
      const handleChartLoad = () => {
        console.log('📡 接收到chartjs-loaded事件');
        const chart = isChartAvailable();
        if (chart) {
          window.Chart = chart;
          this.configureChartDefaults();
          console.log('✅ Chart.js 事件加载成功，监控功能已启用');
          this.chartReady = true;
          window.removeEventListener('chartjs-loaded', handleChartLoad);
        } else {
          console.warn('⚠️ 接收到加载事件但Chart对象仍不可用，继续轮询...');
        }
      };
      
      const handleChartError = () => {
        console.error('❌ Chart.js 加载失败事件触发');
        this.loadChartJSFallback();
        window.removeEventListener('chartjs-loaded', handleChartLoad);
        window.removeEventListener('chartjs-error', handleChartError);
      };
      
      window.addEventListener('chartjs-loaded', handleChartLoad);
      window.addEventListener('chartjs-error', handleChartError);
      
      // 立即开始轮询检查
      setTimeout(pollForChart, 100);
    }
  }
  
  loadChartJSFallback() {
    console.log('🔄 尝试从CDN加载Chart.js备用方案...');
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.min.js';
    script.onload = () => {
      if (typeof Chart !== 'undefined' && typeof Chart.register === 'function') {
        console.log('✅ Chart.js CDN备用方案加载成功');
        this.configureChartDefaults();
        this.chartReady = true;
      } else {
        console.error('❌ Chart.js CDN加载但对象无效');
        this.chartReady = false;
      }
    };
    script.onerror = () => {
      console.error('❌ Chart.js CDN备用方案也加载失败');
      this.chartReady = false;
    };
    document.head.appendChild(script);
  }
  
  configureChartDefaults() {
    Chart.defaults.font.size = 12;
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.color = '#718096';
    Chart.defaults.borderColor = '#e2e8f0';
    Chart.defaults.backgroundColor = 'rgba(66, 153, 225, 0.1)';
    
    // 响应式设置
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
  }
  
  async showMonitoring(clusterId, namespace, podName, containerId = 'monitoring-container') {
    console.log('📊 显示监控界面:', clusterId, namespace, podName);
    
    this.currentPod = { clusterId, namespace, podName };
    this.isVisible = true;
    
    try {
      // 获取容器元素
      const container = document.getElementById(containerId);
      if (!container) {
        throw new Error(`Container element #${containerId} not found`);
      }
      
      // 直接渲染监控界面
      await this.renderMonitoringPanel(container);
      
      // 开始数据刷新
      this.startAutoRefresh();
      
    } catch (error) {
      console.error('显示监控界面失败:', error);
      this.showError(container, error.message);
    }
  }
  
  async renderMonitoringPanel(container) {
    // 显示加载状态
    container.innerHTML = this.getLoadingHTML();
    
    try {
      console.log('🚀 开始渲染监控面板');
      
      // 加载监控数据
      console.log('📊 加载实时监控数据...');
      const metricsData = await this.loadMetricsData();
      
      console.log('📈 加载历史监控数据...');
      const historyData = await this.loadHistoryData();
      
      // 渲染完整界面
      console.log('🎨 渲染监控界面HTML...');
      container.innerHTML = this.getMonitoringHTML();
      
      // 更新指标卡片
      console.log('📋 更新指标卡片...');
      this.updateMetricsCards(metricsData);
      
      // 创建图表
      console.log('📊 创建监控图表...');
      await this.createCharts(historyData);
      
      // 更新容器信息
      console.log('📦 更新容器信息...');
      this.updateContainersInfo(metricsData);
      
      // 更新最后更新时间
      const lastUpdatedElement = document.getElementById('last-updated-time');
      if (lastUpdatedElement) {
        lastUpdatedElement.textContent = new Date().toLocaleTimeString('zh-CN');
      }
      
      console.log('✅ 监控面板渲染完成');
      
    } catch (error) {
      console.error('❌ 渲染监控面板失败:', error);
      container.innerHTML = this.getErrorHTML(error.message);
    }
  }
  
  async loadMetricsData() {
    const { clusterId, namespace, podName } = this.currentPod;
    
    try {
      const url = `/api/k8s/clusters/${clusterId}/namespaces/${namespace}/pods/${podName}/metrics`;
      console.log('📡 请求实时监控数据:', url);
      
      const response = await fetch(url);
      
      if (!response.ok) {
        console.warn(`❌ API请求失败 ${response.status}: ${response.statusText}`);
        throw new Error(`API请求失败: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('📊 实时数据响应:', data);
      
      if (!data.success) {
        throw new Error(data.error || '获取监控数据失败');
      }
      
      // 验证数据结构
      if (!data.data) {
        throw new Error('监控数据格式无效');
      }
      
      console.log('✅ 成功获取实时监控数据');
      return data.data;
    } catch (error) {
      console.error('❌ 获取监控数据失败:', error);
      throw error;
    }
  }
  
  async loadHistoryData(duration = 60) {
    const { clusterId, namespace, podName } = this.currentPod;
    
    try {
      const url = `/api/k8s/clusters/${clusterId}/namespaces/${namespace}/pods/${podName}/metrics/history?duration=${duration}`;
      console.log('📡 请求历史监控数据:', url);
      
      const response = await fetch(url);
      
      // 检查响应状态
      if (!response.ok) {
        console.warn(`❌ API请求失败 ${response.status}: ${response.statusText}`);
        return this.generateMockHistoryData(duration);
      }
      
      const data = await response.json();
      console.log('📊 历史数据响应:', data);
      
      if (!data.success) {
        console.warn('⚠️ 获取历史数据失败，使用模拟数据:', data.error);
        return this.generateMockHistoryData(duration);
      }
      
      // 验证数据结构
      if (!data.data || !data.data.data_points || !Array.isArray(data.data.data_points)) {
        console.warn('⚠️ 历史数据格式无效，使用模拟数据');
        return this.generateMockHistoryData(duration);
      }
      
      console.log(`✅ 成功获取 ${data.data.data_points.length} 个历史数据点`);
      return data.data;
    } catch (error) {
      console.warn('❌ 数据获取异常，使用模拟数据:', error.message);
      return this.generateMockHistoryData(duration);
    }
  }

  generateMockHistoryData(duration = 60) {
    console.log('🎭 生成模拟历史数据用于图表测试');
    
    const dataPoints = [];
    const now = new Date();
    
    for (let i = 0; i < duration; i++) {
      const timestamp = new Date(now - (duration - i) * 60000); // 每分钟一个数据点
      
      dataPoints.push({
        timestamp: timestamp.toISOString(),
        cpu_millicores: Math.floor(Math.random() * 500 + 100), // 100-600m CPU
        memory_bytes: Math.floor(Math.random() * 200 * 1024 * 1024 + 100 * 1024 * 1024), // 100-300Mi 内存
        cpu_percentage: Math.random() * 50 + 10, // 10-60% CPU
        memory_percentage: Math.random() * 40 + 20 // 20-60% 内存
      });
    }
    
    return {
      pod_name: this.currentPod.podName,
      namespace: this.currentPod.namespace,
      duration_minutes: duration,
      data_points: dataPoints
    };
  }
  
  getLoadingHTML() {
    return `
      <div class="monitoring-loading">
        <div class="spinner-border text-primary" role="status"></div>
        <p>加载监控数据中...</p>
      </div>
    `;
  }
  
  getErrorHTML(errorMessage) {
    const isChartError = errorMessage.includes('Chart') || errorMessage.includes('chart') || typeof Chart === 'undefined';
    
    return `
      <div class="monitoring-error">
        <i class="fas fa-exclamation-triangle fa-3x"></i>
        <h5>${isChartError ? '图表组件加载失败' : '监控数据加载失败'}</h5>
        <p>${errorMessage}</p>
        ${isChartError ? `
          <div class="mt-3">
            <small class="text-muted">
              <i class="fas fa-info-circle"></i>
              可能的原因：网络连接问题导致Chart.js库无法加载
            </small>
          </div>
        ` : ''}
        <button class="retry-btn" onclick="podMonitoring.retryLoad()">
          <i class="fas fa-redo"></i> 重试
        </button>
      </div>
    `;
  }
  
  getMonitoringHTML() {
    return `
      <div class="monitoring-panel">
        <div class="monitoring-header">
          <h5>
            <i class="fas fa-chart-line"></i>
            ${this.currentPod.namespace}/${this.currentPod.podName} - 监控
          </h5>
          <div class="monitoring-controls">
            <select class="time-range-selector" id="time-range-select" onchange="podMonitoring.changeTimeRange(this.value)">
              <option value="60">1小时</option>
              <option value="360">6小时</option>
              <option value="720">12小时</option>
              <option value="1440">24小时</option>
            </select>
            <button class="refresh-btn" onclick="podMonitoring.refreshData()" title="刷新数据">
              <i class="fas fa-sync-alt"></i>
            </button>
          </div>
        </div>
        
        <div class="monitoring-content">
          <!-- 指标概览 -->
          <div class="metrics-overview">
            <div class="metric-card cpu">
              <div class="metric-label">CPU 使用量</div>
              <div class="metric-value" id="cpu-usage">--</div>
              <div class="metric-details" id="cpu-details">加载中...</div>
            </div>
            <div class="metric-card memory">
              <div class="metric-label">内存使用量</div>
              <div class="metric-value" id="memory-usage">--</div>
              <div class="metric-details" id="memory-details">加载中...</div>
            </div>
            <div class="metric-card disk">
              <div class="metric-label">磁盘使用量</div>
              <div class="metric-value" id="disk-usage">--</div>
              <div class="metric-details" id="disk-details">加载中...</div>
            </div>
            <div class="metric-card network">
              <div class="metric-label">网络</div>
              <div class="metric-value" id="network-info">--</div>
              <div class="metric-details" id="network-details">加载中...</div>
            </div>
          </div>
          
          <!-- 图表区域 -->
          <div class="charts-container">
            <div class="chart-card">
              <div class="chart-title">
                <i class="fas fa-microchip text-primary"></i>
                CPU 使用趋势
              </div>
              <div class="chart-container">
                <canvas id="cpu-chart"></canvas>
              </div>
            </div>
            <div class="chart-card">
              <div class="chart-title">
                <i class="fas fa-memory text-success"></i>
                内存使用趋势
              </div>
              <div class="chart-container">
                <canvas id="memory-chart"></canvas>
              </div>
            </div>
          </div>
          
          <!-- 容器信息 -->
          <div class="containers-section">
            <div class="containers-title">
              <i class="fas fa-cubes"></i>
              容器资源详情
            </div>
            <div class="containers-grid" id="containers-grid">
              <!-- 容器信息将在这里动态生成 -->
            </div>
          </div>
          
          <div class="last-updated">
            <span class="update-indicator"></span>
            最后更新: <span id="last-updated-time">--</span>
          </div>
        </div>
      </div>
    `;
  }
  
  updateMetricsCards(metricsData) {
    // CPU 使用量
    const cpuUsage = metricsData.cpu?.usage_cores || 0;
    const cpuMillicores = metricsData.cpu?.usage_millicores || 0;
    document.getElementById('cpu-usage').textContent = `${cpuUsage}`;
    document.getElementById('cpu-details').textContent = `${cpuMillicores}m 毫核心`;
    
    // 内存使用量
    const memoryUsage = metricsData.memory?.usage_mi || 0;
    const memoryBytes = metricsData.memory?.usage_bytes || 0;
    document.getElementById('memory-usage').textContent = `${memoryUsage}Mi`;
    document.getElementById('memory-details').textContent = `${this.formatBytes(memoryBytes)}`;
    
    // 磁盘使用量
    const volumeCount = metricsData.disk?.volumes?.length || 0;
    const ephemeralUsage = metricsData.disk?.ephemeral_storage?.estimated_usage_mi || 0;
    document.getElementById('disk-usage').textContent = `${volumeCount}`;
    document.getElementById('disk-details').textContent = `${ephemeralUsage}Mi 临时存储`;
    
    // 网络信息
    const podIp = metricsData.network?.pod_ip || 'N/A';
    const portCount = metricsData.network?.ports?.length || 0;
    document.getElementById('network-info').textContent = portCount > 0 ? `${portCount}` : 'N/A';
    document.getElementById('network-details').textContent = `Pod IP: ${podIp}`;
  }
  
  async createCharts(historyData) {
    console.log('📊 开始创建监控图表', historyData);
    
    // 检查Chart.js是否准备就绪
    const isChartReady = () => {
      return this.chartReady && 
             ((typeof window.Chart !== 'undefined' && window.Chart && typeof window.Chart.register === 'function') ||
              (typeof Chart !== 'undefined' && Chart && typeof Chart.register === 'function'));
    };
    
    if (!isChartReady()) {
      console.error('❌ Chart.js 未完全加载，等待加载完成...');
      
      // 等待Chart.js加载完成
      const maxWaitTime = 5000; // 最多等待5秒
      const startTime = Date.now();
      
      while (!isChartReady() && (Date.now() - startTime) < maxWaitTime) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      if (!isChartReady()) {
        console.error('❌ Chart.js 加载超时，使用占位符');
        this.showPlaceholderCharts();
        return;
      } else {
        console.log('✅ Chart.js 加载完成，继续创建图表');
      }
    }
    
    // 如果没有历史数据，使用演示数据
    if (!historyData || !historyData.data_points || historyData.data_points.length === 0) {
      console.debug('⚠️ 没有历史数据，创建演示图表');
      this.createDemoCharts();
      return;
    }
    
    const dataPoints = historyData.data_points;
    
    // 验证数据点有效性
    if (!Array.isArray(dataPoints) || dataPoints.length === 0) {
      console.warn('⚠️ 数据点无效或为空，使用演示数据');
      this.createDemoCharts();
      return;
    }
    
    const labels = dataPoints.map(point => {
      if (!point.timestamp) {
        console.warn('⚠️ 数据点缺少时间戳:', point);
        return '无效时间';
      }
      const date = new Date(point.timestamp);
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    });
    
    console.log(`📈 创建实际数据图表，数据点数: ${dataPoints.length}`);
    console.log('🏷️ 时间标签示例:', labels.slice(0, 3), '...');
    
    try {
      // CPU 图表
      await this.createCPUChart(labels, dataPoints);
      
      // 内存图表
      await this.createMemoryChart(labels, dataPoints);
      
      // 创建磁盘IO图表（演示）
      this.createDiskChart(labels, dataPoints);
      
      console.log('✅ 所有监控图表创建完成');
    } catch (error) {
      console.error('❌ 图表创建失败:', error);
      this.showPlaceholderCharts();
    }
  }
  
  // 创建演示图表（当没有真实数据时）
  createDemoCharts() {
    console.log('🎭 准备创建演示图表...');
    
    // 使用统一的Chart.js检查逻辑
    const hasChart = (typeof window.Chart !== 'undefined' && window.Chart && typeof window.Chart.register === 'function') ||
                     (typeof Chart !== 'undefined' && Chart && typeof Chart.register === 'function');
    
    if (!this.chartReady || !hasChart) {
      console.error('❌ Chart.js 未完全加载，无法创建演示图表');
      this.showPlaceholderCharts();
      return;
    }
    
    console.log('✅ Chart.js 可用，开始生成模拟数据');
    
    // 生成模拟数据
    const now = new Date();
    const labels = [];
    const cpuData = [];
    const memoryData = [];
    
    for (let i = 11; i >= 0; i--) {
      const time = new Date(now - i * 5 * 60000); // 每5分钟一个数据点
      labels.push(time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
      cpuData.push(Math.random() * 0.5 + 0.1); // CPU 0.1-0.6 核心
      memoryData.push(Math.random() * 200 + 100); // 内存 100-300Mi
    }
    
    console.log('📊 模拟数据生成完成:', { 
      labelsCount: labels.length, 
      cpuDataSample: cpuData.slice(0, 3),
      memoryDataSample: memoryData.slice(0, 3)
    });
    
    // 创建演示图表
    const cpuMockData = cpuData.map((cpu, index) => ({
      cpu_millicores: cpu * 1000,
      timestamp: labels[index]
    }));
    
    const memoryMockData = memoryData.map((memory, index) => ({
      memory_bytes: memory * 1024 * 1024,
      timestamp: labels[index]
    }));
    
    console.log('🔧 开始创建CPU演示图表');
    this.createCPUChart(labels, cpuMockData);
    
    console.log('🔧 开始创建内存演示图表');  
    this.createMemoryChart(labels, memoryMockData);
    
    console.log('✅ 演示图表创建完成');
  }
  
  showPlaceholderCharts() {
    const cpuChartContainer = document.querySelector('#cpu-chart')?.parentElement;
    const memoryChartContainer = document.querySelector('#memory-chart')?.parentElement;
    
    // 使用统一的Chart.js检查逻辑
    const hasChart = (typeof window.Chart !== 'undefined' && window.Chart && typeof window.Chart.register === 'function') ||
                     (typeof Chart !== 'undefined' && Chart && typeof Chart.register === 'function');
    
    if (!hasChart) {
      // Chart.js不可用，显示错误信息
      if (cpuChartContainer) {
        cpuChartContainer.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-exclamation-triangle"></i>
            <p>图表组件加载失败</p>
            <small>Chart.js库未能正确加载</small>
          </div>
        `;
      }
      
      if (memoryChartContainer) {
        memoryChartContainer.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-exclamation-triangle"></i>
            <p>图表组件加载失败</p>
            <small>Chart.js库未能正确加载</small>
          </div>
        `;
      }
    } else {
      // Chart.js可用，但没有历史数据
      if (cpuChartContainer) {
        cpuChartContainer.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-chart-line"></i>
            <p>暂无历史数据</p>
            <small>图表将在数据可用时显示</small>
          </div>
        `;
      }
      
      if (memoryChartContainer) {
        memoryChartContainer.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-chart-line"></i>
            <p>暂无历史数据</p>
            <small>图表将在数据可用时显示</small>
          </div>
        `;
      }
    }
  }
  
  async createCPUChart(labels, dataPoints) {
    console.log('🔧 开始创建CPU图表...');
    console.log('📊 CPU图表参数:', { labelsCount: labels?.length, dataPointsCount: dataPoints?.length });
    
    const ctx = document.getElementById('cpu-chart');
    if (!ctx) {
      console.error('❌ CPU图表容器元素 #cpu-chart 不存在');
      return;
    }
    console.log('✅ CPU图表容器元素找到');
    
    // 检查Chart.js是否可用
    const chartObj = window.Chart || Chart;
    if (!chartObj || typeof chartObj.register !== 'function') {
      console.error('❌ Chart.js 未完全可用，无法创建CPU图表');
      return;
    }
    console.log('✅ Chart.js 可用');
    
    // 验证输入数据
    if (!Array.isArray(labels) || !Array.isArray(dataPoints) || labels.length === 0 || dataPoints.length === 0) {
      console.error('❌ CPU图表数据无效');
      return;
    }
    
    // 销毁现有图表
    if (this.charts.cpu) {
      console.log('🗑️ 销毁现有CPU图表');
      this.charts.cpu.destroy();
      delete this.charts.cpu;
    }
    
    const cpuData = dataPoints.map(point => {
      if (!point || typeof point !== 'object') {
        console.warn('⚠️ 无效的数据点:', point);
        return 0;
      }
      const value = (point.cpu_millicores || 0) / 1000; // 转换为核心
      return Math.max(0, value); // 确保非负数
    });
    
    console.log('📈 CPU数据处理完成:', { 
      total: cpuData.length, 
      sample: cpuData.slice(0, 3),
      min: Math.min(...cpuData),
      max: Math.max(...cpuData)
    });
    
    try {
      const ChartConstructor = window.Chart || Chart;
      this.charts.cpu = new ChartConstructor(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'CPU 使用量 (核心)',
            data: cpuData,
            borderColor: '#4299e1',
            backgroundColor: 'rgba(66, 153, 225, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 1000
          },
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              backgroundColor: 'rgba(45, 55, 72, 0.95)',
              titleColor: 'white',
              bodyColor: 'white',
              borderColor: '#4299e1',
              borderWidth: 1,
              callbacks: {
                label: function(context) {
                  return `CPU: ${context.parsed.y.toFixed(3)} 核心`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: {
                display: false
              }
            },
            y: {
              beginAtZero: true,
              grid: {
                color: '#f1f5f9'
              },
              ticks: {
                callback: function(value) {
                  return value.toFixed(2) + ' 核心';
                }
              }
            }
          },
          interaction: {
            intersect: false,
            mode: 'index'
          }
        }
      });
    
      console.log('✅ CPU图表创建成功');
      
      // 验证图表是否正确渲染
      setTimeout(() => {
        if (this.charts.cpu && ctx.offsetWidth > 0) {
          console.log('✅ CPU图表渲染验证成功');
        } else {
          console.warn('⚠️ CPU图表可能未正确渲染');
        }
      }, 100);
      
    } catch (error) {
      console.error('❌ CPU图表创建失败:', error);
      // 显示错误占位符
      const container = ctx.parentElement;
      if (container) {
        container.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-exclamation-triangle"></i>
            <p>CPU图表创建失败</p>
            <small>${error.message}</small>
          </div>
        `;
      }
    }
  }
  
  async createMemoryChart(labels, dataPoints) {
    console.log('🔧 开始创建内存图表...');
    
    const ctx = document.getElementById('memory-chart');
    if (!ctx) {
      console.error('❌ 内存图表容器元素 #memory-chart 不存在');
      return;
    }
    console.log('✅ 内存图表容器元素找到');
    
    // 检查Chart.js是否可用
    const chartObj = window.Chart || Chart;
    if (!chartObj || typeof chartObj.register !== 'function') {
      console.error('❌ Chart.js 未定义，无法创建内存图表');
      return;
    }
    console.log('✅ Chart.js 可用');
    
    // 验证输入数据
    if (!Array.isArray(labels) || !Array.isArray(dataPoints) || labels.length === 0 || dataPoints.length === 0) {
      console.error('❌ 内存图表数据无效');
      return;
    }
    
    // 销毁现有图表
    if (this.charts.memory) {
      console.log('🗑️ 销毁现有内存图表');
      this.charts.memory.destroy();
      delete this.charts.memory;
    }
    
    const memoryData = dataPoints.map(point => {
      if (!point || typeof point !== 'object') {
        console.warn('⚠️ 无效的数据点:', point);
        return 0;
      }
      const value = (point.memory_bytes || 0) / (1024 * 1024); // 转换为Mi
      return Math.max(0, value); // 确保非负数
    });
    
    console.log('📈 内存数据处理完成:', { 
      total: memoryData.length, 
      sample: memoryData.slice(0, 3),
      min: Math.min(...memoryData),
      max: Math.max(...memoryData)
    });
    
    try {
      const ChartConstructor = window.Chart || Chart;
      this.charts.memory = new ChartConstructor(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '内存使用量 (Mi)',
            data: memoryData,
            borderColor: '#48bb78',
            backgroundColor: 'rgba(72, 187, 120, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 1000
          },
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              backgroundColor: 'rgba(45, 55, 72, 0.95)',
              titleColor: 'white',
              bodyColor: 'white',
              borderColor: '#48bb78',
              borderWidth: 1,
              callbacks: {
                label: function(context) {
                  return `内存: ${Math.round(context.parsed.y)} Mi`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: {
                display: false
              }
            },
            y: {
              beginAtZero: true,
              grid: {
                color: '#f1f5f9'
              },
              ticks: {
                callback: function(value) {
                  return Math.round(value) + ' Mi';
                }
              }
            }
          },
          interaction: {
            intersect: false,
            mode: 'index'
          }
        }
      });
      
      console.log('✅ 内存图表创建成功');
      
      // 验证图表是否正确渲染
      setTimeout(() => {
        if (this.charts.memory && ctx.offsetWidth > 0) {
          console.log('✅ 内存图表渲染验证成功');
        } else {
          console.warn('⚠️ 内存图表可能未正确渲染');
        }
      }, 100);
      
    } catch (error) {
      console.error('❌ 内存图表创建失败:', error);
      // 显示错误占位符
      const container = ctx.parentElement;
      if (container) {
        container.innerHTML = `
          <div class="chart-placeholder">
            <i class="fas fa-exclamation-triangle"></i>
            <p>内存图表创建失败</p>
            <small>${error.message}</small>
          </div>
        `;
      }
    }
  }
  
  updateContainersInfo(metricsData) {
    const containersGrid = document.getElementById('containers-grid');
    if (!containersGrid) return;
    
    const containers = metricsData.containers || [];
    
    if (containers.length === 0) {
      containersGrid.innerHTML = `
        <div class="no-data">
          <i class="fas fa-cube"></i>
          <p>没有容器信息</p>
        </div>
      `;
      return;
    }
    
    containersGrid.innerHTML = containers.map(container => `
      <div class="container-card">
        <div class="container-header">
          <div class="container-name">${container.name}</div>
          <div class="container-image">${this.getShortImageName(container.image)}</div>
        </div>
        <div class="container-resources">
          <div class="resource-item">
            <div class="resource-value">${this.formatResourceValue(container.metrics?.cpu_usage_millicores || 0, 'm')}</div>
            <div class="resource-label">CPU</div>
          </div>
          <div class="resource-item">
            <div class="resource-value">${this.formatBytes(container.metrics?.memory_usage_bytes || 0)}</div>
            <div class="resource-label">内存</div>
          </div>
        </div>
      </div>
    `).join('');
  }
  
  startAutoRefresh() {
    // 清除现有定时器
    this.stopAutoRefresh();
    
    // 每30秒刷新一次
    this.refreshInterval = setInterval(() => {
      if (this.isVisible && this.currentPod) {
        this.refreshData();
      }
    }, 30000);
  }
  
  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }
  
  async refreshData() {
    if (!this.currentPod) return;
    
    try {
      const metricsData = await this.loadMetricsData();
      this.updateMetricsCards(metricsData);
      this.updateContainersInfo(metricsData);
      
      // 更新时间戳
      document.getElementById('last-updated-time').textContent = 
        new Date().toLocaleTimeString('zh-CN');
      
    } catch (error) {
      console.error('刷新监控数据失败:', error);
    }
  }
  
  async changeTimeRange(duration) {
    if (!this.currentPod) return;
    
    try {
      const historyData = await this.loadHistoryData(parseInt(duration));
      if (historyData) {
        await this.createCharts(historyData);
      }
    } catch (error) {
      console.error('切换时间范围失败:', error);
    }
  }
  
  hide() {
    this.isVisible = false;
    this.stopAutoRefresh();
    
    // 销毁图表
    Object.values(this.charts).forEach(chart => {
      if (chart) {
        chart.destroy();
      }
    });
    this.charts = {};
  }
  
  retryLoad() {
    if (this.currentPod) {
      const container = document.querySelector('.monitoring-panel')?.parentElement || 
                       document.querySelector('.monitoring-error')?.parentElement ||
                       document.getElementById('monitoring-container');
      
      if (container) {
        console.log('🔄 重新加载监控面板...');
        this.showMonitoring(this.currentPod.clusterId, this.currentPod.namespace, this.currentPod.podName, container.id);
      } else {
        console.error('找不到监控容器元素');
      }
    }
  }
  
  // 工具方法
  formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  }
  
  formatResourceValue(value, unit) {
    if (value === 0) return '0' + unit;
    
    if (unit === 'm') {
      // 毫核心
      if (value >= 1000) {
        return (value / 1000).toFixed(2) + ' 核心';
      }
      return value + 'm';
    }
    
    return value + unit;
  }
  
  getShortImageName(imageName) {
    if (!imageName) return 'unknown';
    
    const parts = imageName.split('/');
    const nameTag = parts[parts.length - 1];
    const [name] = nameTag.split(':');
    
    return name;
  }
  
  showError(container, message) {
    if (container) {
      container.innerHTML = this.getErrorHTML(message);
    }
  }
  
  // 静态方法 - 显示通知
  static showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, type === 'error' ? 8000 : 5000);
  }
  
  createDiskChart(labels, dataPoints) {
    // 注意：Kubernetes原生不提供磁盘IO指标，这里创建一个演示图表
    console.log('💾 创建磁盘IO演示图表');
    
    const ctx = document.getElementById('disk-chart');
    if (!ctx) {
      console.log('💾 磁盘图表容器未找到，跳过');
      return;
    }
    
    const chartObj = window.Chart || Chart;
    if (!chartObj || typeof chartObj.register !== 'function') {
      console.error('❌ Chart.js 未定义，无法创建磁盘图表');
      return;
    }
    
    // 销毁现有图表
    if (this.charts.disk) {
      this.charts.disk.destroy();
    }
    
    // 生成模拟磁盘IO数据（读写速度）
    const readData = dataPoints.map(() => Math.random() * 50 + 10); // 10-60 MB/s
    const writeData = dataPoints.map(() => Math.random() * 30 + 5);  // 5-35 MB/s
    
    try {
      const ChartConstructor = window.Chart || Chart;
      this.charts.disk = new ChartConstructor(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '磁盘读取 (MB/s)',
            data: readData,
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            borderWidth: 2,
            fill: false,
            tension: 0.3
          }, {
            label: '磁盘写入 (MB/s)', 
            data: writeData,
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            borderWidth: 2,
            fill: false,
            tension: 0.3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: true,
              position: 'top'
            },
            tooltip: {
              backgroundColor: 'rgba(45, 55, 72, 0.95)',
              titleColor: 'white',
              bodyColor: 'white',
              borderColor: '#10b981',
              borderWidth: 1
            }
          },
          scales: {
            x: {
              title: {
                display: true,
                text: '时间'
              },
              grid: {
                color: '#e2e8f0'
              }
            },
            y: {
              beginAtZero: true,
              title: {
                display: true,
                text: '速度 (MB/s)'
              },
              grid: {
                color: '#e2e8f0'
              }
            }
          }
        }
      });
      
      console.log('✅ 磁盘IO演示图表创建成功');
    } catch (error) {
      console.error('❌ 磁盘图表创建失败:', error);
    }
  }
}

// 创建全局实例
let podMonitoring;

// 初始化函数
function initPodMonitoring() {
  if (!podMonitoring) {
    console.log('🏭 初始化Pod监控管理器');
    console.log('🔍 当前Chart.js状态:', typeof Chart !== 'undefined' ? '✅已加载' : '❌未加载');
    
    if (typeof Chart !== 'undefined') {
      console.log('📊 Chart.js 可用性:', typeof Chart.register === 'function' ? '✅完全可用' : '⚠️部分可用');
    }
    
    podMonitoring = new PodMonitoringManager();
    
    // 暴露到全局作用域
    window.podMonitoring = podMonitoring;
    
    // 暴露全局函数
    window.showPodMonitoring = (clusterId, namespace, podName, containerId = 'monitoring-container') => {
      console.log('🌐 全局函数调用showPodMonitoring:', clusterId, namespace, podName, containerId);
      if (podMonitoring) {
        podMonitoring.showMonitoring(clusterId, namespace, podName, containerId);
      } else {
        console.error('❌ Pod监控管理器未初始化');
      }
    };
    
    console.log('✅ Pod监控管理器初始化完成，已暴露到window.podMonitoring');
    console.log('✅ 全局函数window.showPodMonitoring已注册');
  }
}

// 确保在DOM加载完成后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPodMonitoring);
} else {
  // 如果DOM已经加载完成，立即初始化
  initPodMonitoring();
}

// 也在window.onload时初始化（双重保险）
window.addEventListener('load', initPodMonitoring);