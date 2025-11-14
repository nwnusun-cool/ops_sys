/**
 * 简化的侧边栏菜单交互脚本
 * 扁平化菜单结构，移除下拉菜单逻辑
 */

console.log('🚀 侧边栏菜单脚本已加载');

class SidebarMenu {
  constructor() {
    this.isInitialized = false;
    this.init();
  }

  init() {
    if (this.isInitialized) return;
    
    this.highlightActiveMenu();
    this.addKeyboardNavigation();
    this.handleMobileMenu();
    this.isInitialized = true;
    
    console.log('✅ 侧边栏菜单初始化完成');
  }

  /**
   * 高亮当前活跃的菜单项
   */
  highlightActiveMenu() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar .nav-link, .offcanvas .nav-link');
    
    navLinks.forEach(link => {
      const href = link.getAttribute('href');
      
      // 精确匹配当前路径
      if (href === currentPath) {
        link.classList.add('active');
      } else {
        link.classList.remove('active');
      }
    });
    
    console.log('✅ 菜单高亮已更新');
  }

  /**
   * 添加键盘导航支持
   */
  addKeyboardNavigation() {
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    
    navLinks.forEach((link, index) => {
      link.addEventListener('keydown', (e) => {
        // 支持上下箭头键导航
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const nextLink = navLinks[index + 1];
          if (nextLink) nextLink.focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prevLink = navLinks[index - 1];
          if (prevLink) prevLink.focus();
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          link.click();
        }
      });
    });
    
    console.log('✅ 键盘导航已启用');
  }

  /**
   * 处理移动端汉堡菜单
   */
  handleMobileMenu() {
    const offcanvas = document.getElementById('sidebarOffcanvas');
    
    if (offcanvas) {
      // 点击菜单项后自动关闭移动端菜单
      const mobileLinks = offcanvas.querySelectorAll('.nav-link');
      
      mobileLinks.forEach(link => {
        link.addEventListener('click', () => {
          // 使用Bootstrap的offcanvas API关闭菜单
          const bsOffcanvas = bootstrap.Offcanvas.getInstance(offcanvas);
          if (bsOffcanvas) {
            bsOffcanvas.hide();
          }
        });
      });
      
      console.log('✅ 移动端菜单处理已启用');
    }
  }

  /**
   * 刷新菜单高亮（用于SPA或动态路由）
   */
  refresh() {
    this.highlightActiveMenu();
  }

  /**
   * 销毁方法
   */
  destroy() {
    this.isInitialized = false;
    console.log('🗑️ 侧边栏菜单已销毁');
  }
}

// 等待DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
  // 创建全局实例
  window.sidebarMenu = new SidebarMenu();
  
  console.log('🎉 侧边栏菜单已启用');
});

// 导出类以供其他脚本使用
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SidebarMenu;
}