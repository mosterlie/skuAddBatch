chrome.action.onClicked.addListener((tab) => {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['content.js']
  });
});

// 突破 HTTPS 网页对 HTTP 本地服务 (localhost:31415) 的 Mixed Content 限制
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'FETCH_IMAGE') {
    const imgUrl = 'http://localhost:31415/?path=' + encodeURIComponent(request.path);
    fetch(imgUrl)
      .then(res => {
        if (!res.ok) throw new Error('HTTP status ' + res.status);
        return res.blob();
      })
      .then(blob => {
        const reader = new FileReader();
        reader.onloadend = () => {
          sendResponse({ success: true, dataUrl: reader.result, type: blob.type });
        };
        reader.readAsDataURL(blob);
      })
      .catch(err => {
        console.error('Background fetch local image failed:', err);
        sendResponse({ success: false, error: err.message });
      });
    return true; // 维持异步消息通道
  }
});

