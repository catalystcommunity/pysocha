// Only presentation metadata crosses the native bridge.
if (window === window.top) {
  const report = async () => {
    const page = location.href;
    const icon = document.querySelector('link[rel~="icon"]')?.href;
    let png = '';
    try {
      const image = new Image();
      image.crossOrigin = 'anonymous';
      image.src = icon || new URL('/favicon.ico', page).href;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 32;
      canvas.getContext('2d').drawImage(image, 0, 0, 32, 32);
      png = canvas.toDataURL('image/png').split(',')[1];
    } catch {}
    if (page === location.href) window.ipc.postMessage(JSON.stringify({page, title: document.title, png}));
  };
  window.addEventListener('DOMContentLoaded', () => {
    report();
    if (document.head) new MutationObserver(report).observe(document.head, {
      subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['href', 'rel']
    });
  });
}
