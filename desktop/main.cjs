const { app, BrowserWindow, ipcMain, shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const VERSION = "0.4.7";
const MANIFEST_URL =
  "https://github.com/Alexis-Tissier/detour/releases/download/data-france-v1/detour-data-france-v1.json";

let window = null;
let graphhopper = null;
let backend = null;

function dataRoot() {
  if (process.platform === "win32") {
    return path.join(process.env.LOCALAPPDATA || app.getPath("userData"), "Detour");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "Detour");
  }
  return path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local", "share"), "detour");
}

function resourcesRoot() {
  return app.isPackaged
    ? process.resourcesPath
    : path.resolve(__dirname, "..", "build", "desktop", "runtime");
}

function backendBinary() {
  const suffix = process.platform === "win32" ? ".exe" : "";
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend", `detour-backend${suffix}`)
    : path.resolve(
        __dirname,
        "..",
        "build",
        "desktop",
        "python",
        "detour-backend",
        `detour-backend${suffix}`,
      );
}

function javaBinary() {
  return path.join(resourcesRoot(), "jre", "bin", process.platform === "win32" ? "java.exe" : "java");
}

function graphhopperJar() {
  return path.join(resourcesRoot(), "graphhopper", "graphhopper-web-11.0.jar");
}

function graphhopperHeapGiB() {
  const totalGiB = os.totalmem() / 1024 ** 3;
  return Math.max(2, Math.min(8, Math.floor(totalGiB * 0.5)));
}

function graphhopperTemplate() {
  return path.join(resourcesRoot(), "infra", "graphhopper", "config.yml");
}

function customModelsDir() {
  return path.join(resourcesRoot(), "infra", "graphhopper", "custom_models");
}

function sendStatus(message, detail = "", progress = null) {
  if (window && !window.isDestroyed()) {
    window.webContents.send("detour-status", { message, detail, progress });
  }
}

function installedPack() {
  const pointer = path.join(dataRoot(), "current-france.json");
  if (!fs.existsSync(pointer)) return null;
  try {
    const pack = JSON.parse(fs.readFileSync(pointer, "utf8")).path;
    const required = [
      path.join(pack, "graph-cache"),
      path.join(pack, "ban.sqlite"),
      path.join(pack, "communes.sqlite"),
    ];
    return required.every(fs.existsSync) ? pack : null;
  } catch {
    return null;
  }
}

function waitHttp(url, timeoutMs, processRef) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const attempt = () => {
      if (processRef && processRef.exitCode !== null) {
        reject(new Error(`Le moteur s'est arrêté avec le code ${processRef.exitCode}.`));
        return;
      }
      const request = http.get(url, (response) => {
        response.resume();
        if (response.statusCode >= 200 && response.statusCode < 500) resolve();
        else retry();
      });
      request.setTimeout(1500, () => request.destroy());
      request.on("error", retry);
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`Délai dépassé pour ${url}`));
      } else {
        setTimeout(attempt, 500);
      }
    };
    attempt();
  });
}

function installData() {
  return new Promise((resolve, reject) => {
    const child = spawn(
      backendBinary(),
      ["install-data", "--manifest-url", MANIFEST_URL, "--data-root", dataRoot()],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let buffer = "";
    let errors = "";

    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("DETOUR_EVENT ")) continue;
        try {
          const event = JSON.parse(line.slice("DETOUR_EVENT ".length));
          if (event.event === "download") {
            sendStatus(
              "Téléchargement des données France",
              `${event.name} — ${Number(event.percent).toFixed(1)} %`,
              event.percent,
            );
          } else if (event.event === "verify-part") {
            sendStatus("Vérification du téléchargement", event.name, null);
          } else if (event.event === "assemble") {
            sendStatus("Assemblage des données", "", null);
          } else if (event.event === "verify-archive") {
            sendStatus("Vérification complète", "Contrôle SHA-256", null);
          } else if (event.event.startsWith("extract")) {
            sendStatus(
              "Installation des données",
              event.total ? `${event.current} / ${event.total}` : "Extraction du pack France",
              null,
            );
          } else if (event.event === "ready") {
            sendStatus("Données prêtes", event.reused ? "Pack local réutilisé" : "Installation terminée", 100);
          }
        } catch {
          // Diagnostic non structuré ignoré.
        }
      }
    });
    child.stderr.on("data", (chunk) => {
      errors += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(errors || `Installation interrompue (${code}).`));
    });
  });
}

function createRuntimeConfig(pack) {
  const runtime = path.join(dataRoot(), "runtime");
  fs.mkdirSync(runtime, { recursive: true });
  const target = path.join(runtime, "graphhopper.yml");
  const normalize = (value) => value.replaceAll("\\", "/");
  let content = fs.readFileSync(graphhopperTemplate(), "utf8");
  content = content.replace(
    /^\s*datareader\.file:.*$/m,
    `  datareader.file: ${normalize(path.join(pack, "unused.osm.pbf"))}`,
  );
  content = content.replace(
    /^\s*graph\.location:.*$/m,
    `  graph.location: ${normalize(path.join(pack, "graph-cache"))}`,
  );
  content = content.replace(
    /^\s*custom_models\.directory:.*$/m,
    `  custom_models.directory: ${normalize(customModelsDir())}`,
  );
  fs.writeFileSync(target, content, "utf8");
  return target;
}

function logFile(name) {
  const logs = path.join(dataRoot(), "logs");
  fs.mkdirSync(logs, { recursive: true });
  return fs.openSync(path.join(logs, name), "a");
}

async function startServices(pack) {
  sendStatus("Démarrage du moteur routier", "GraphHopper", null);
  graphhopper = spawn(
    javaBinary(),
    ["-Xms512m", `-Xmx${graphhopperHeapGiB()}g`, "-jar", graphhopperJar(), "server", createRuntimeConfig(pack)],
    { cwd: dataRoot(), stdio: ["ignore", logFile("graphhopper.log"), logFile("graphhopper.log")] },
  );
  await waitHttp("http://127.0.0.1:8989/info", 120000, graphhopper);

  sendStatus("Démarrage de Détour", "Interface et calculs", null);
  backend = spawn(
    backendBinary(),
    ["serve", "--data-dir", pack, "--graphhopper-url", "http://127.0.0.1:8989"],
    { stdio: ["ignore", logFile("detour.log"), logFile("detour.log")] },
  );
  await waitHttp("http://127.0.0.1:8000/api/health", 60000, backend);
}

function terminate(child) {
  if (child && child.exitCode === null) {
    try {
      child.kill("SIGTERM");
    } catch {
      // Déjà arrêté.
    }
  }
}

function selfTest() {
  const required = [
    backendBinary(),
    javaBinary(),
    graphhopperJar(),
    graphhopperTemplate(),
    customModelsDir(),
  ];
  const missing = required.filter((item) => !fs.existsSync(item));
  if (missing.length) {
    console.error("Ressources absentes :\n" + missing.join("\n"));
    return 1;
  }
  const backendCheck = spawnSync(backendBinary(), ["--version"], { encoding: "utf8" });
  const javaCheck = spawnSync(javaBinary(), ["-version"], { encoding: "utf8" });
  if (backendCheck.status !== 0 || javaCheck.status !== 0) return 1;
  console.log(`Détour Desktop ${VERSION} : ressources valides.`);
  return 0;
}

async function bootstrap() {
  try {
    let pack = installedPack();
    if (!pack) {
      sendStatus("Premier lancement", "Téléchargement unique du pack France", 0);
      await installData();
      pack = installedPack();
    } else {
      sendStatus("Données locales trouvées", "Aucun téléchargement nécessaire", 100);
    }
    if (!pack) throw new Error("Le pack France n'est pas disponible.");
    await startServices(pack);
    sendStatus("Détour est prêt", "", 100);
    await window.loadURL("http://127.0.0.1:8000");
  } catch (error) {
    sendStatus("Démarrage impossible", error.message || String(error), null);
    window.webContents.send("detour-error", error.message || String(error));
  }
}

app.whenReady().then(async () => {
  if (process.argv.includes("--self-test")) {
    app.exit(selfTest());
    return;
  }

  window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: "Détour",
    backgroundColor: "#f7f6f1",
    icon: path.join(__dirname, "assets", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.removeMenu();
  window.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  window.once("ready-to-show", () => window.show());
  await window.loadFile(path.join(__dirname, "loading.html"));
  bootstrap();
});

app.on("before-quit", () => {
  terminate(backend);
  terminate(graphhopper);
});
app.on("window-all-closed", () => app.quit());

ipcMain.handle("open-data-folder", () => shell.openPath(dataRoot()));
