// The page can update the preview tab's label and image.
if (window === window.top) {
  let generation = 0;
  const report = async () => {
    const current = ++generation;
    const page = location.href;
    const title = document.title || location.pathname.split('/').pop() || location.host;
    const send = png => window.ipc.postMessage(JSON.stringify({page, title, png}));
    send('');
    const icons = Array.from(document.querySelectorAll('link[rel~="icon" i]'))
      .filter(link => !link.media || matchMedia(link.media).matches);
    const icon = icons.reverse().find(link => link.sizes.contains('32x32') || link.sizes.contains('any')) || icons[0];
    try {
      const image = new Image();
      image.crossOrigin = 'anonymous';
      image.src = icon?.href || new URL('/favicon.ico', page).href;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 32;
      canvas.getContext('2d').drawImage(image, 0, 0, 32, 32);
      if (generation === current && page === location.href) send(canvas.toDataURL('image/png').split(',')[1]);
    } catch {}
  };
  window.addEventListener('DOMContentLoaded', () => {
    report();
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', report);
    if (document.head) new MutationObserver(report).observe(document.head, {
      subtree: true, childList: true, characterData: true, attributes: true,
      attributeFilter: ['href', 'rel', 'media', 'sizes']
    });
  });
}
