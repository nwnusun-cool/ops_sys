/* jshint esversion: 6 */

/* jshint strict: false */

function checkPassword() {
    const password = document.getElementById('passwordInput').value;
    const errorMessage = document.getElementById('errorMessage');
    const content = document.getElementById('content');

    // 发送密码到后端验证
    fetch('/api/cloud/check-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({password: password})
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 密码正确，显示页面内容
                content.style.display = 'block';
                document.querySelector('.password-container').style.display = 'none';
            } else {
                // 密码错误，显示错误信息
                errorMessage.textContent = data.message || '密码错误，请重试！';
            }
        })
        .catch(error => {
            errorMessage.textContent = '验证密码时发生错误';
        });
}
