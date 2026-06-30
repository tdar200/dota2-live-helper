// Reconnecting WebSocket: calls onMessage(payload) and onStatus(bool).
export function connect(url, onMessage, onStatus) {
  let ws;
  const open = () => {
    ws = new WebSocket(url);
    ws.onopen = () => onStatus(true);
    ws.onclose = () => {
      onStatus(false);
      setTimeout(open, 1000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (_) {}
    };
  };
  open();
}
