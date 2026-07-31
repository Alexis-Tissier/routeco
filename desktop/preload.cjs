const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("detourDesktop", {
  onStatus: (callback) => ipcRenderer.on("detour-status", (_event, payload) => callback(payload)),
  onError: (callback) => ipcRenderer.on("detour-error", (_event, message) => callback(message)),
  openDataFolder: () => ipcRenderer.invoke("open-data-folder"),
});
