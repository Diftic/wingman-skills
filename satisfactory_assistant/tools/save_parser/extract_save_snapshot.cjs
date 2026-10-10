#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const PRODUCTION_CLASS_PATTERN =
  /Build_(Constructor|Assembler|Manufacturer|Smelter|Foundry|Blender|Packager|OilRefinery|HadronCollider|Converter|QuantumEncoder|Miner|OilPump|WaterPump|FrackingExtractor|FrackingSmasher)/;

function usage() {
  return [
    "Usage: node extract_save_snapshot.cjs <save.sav> [--summary-only] [--pretty]",
    "",
    "Parser lookup order:",
    "  SATISFACTORY_PARSER_MODULE   absolute @etothepii/satisfactory-file-parser module directory",
    "  SATISFACTORY_PARSER_RUNTIME  directory containing node_modules/",
    "  local node_modules next to this script",
  ].join("\n");
}

function parseArgs(argv) {
  const options = {
    savePath: null,
    pretty: false,
    summaryOnly: false,
  };

  for (const arg of argv) {
    if (arg === "--pretty") {
      options.pretty = true;
    } else if (arg === "--summary-only") {
      options.summaryOnly = true;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (!options.savePath) {
      options.savePath = arg;
    } else {
      throw new Error(`Unexpected argument: ${arg}`);
    }
  }
  return options;
}

function parserCandidates() {
  const candidates = [];
  if (process.env.SATISFACTORY_PARSER_MODULE) {
    candidates.push(process.env.SATISFACTORY_PARSER_MODULE);
  }
  if (process.env.SATISFACTORY_PARSER_RUNTIME) {
    candidates.push(
      path.join(
        process.env.SATISFACTORY_PARSER_RUNTIME,
        "node_modules",
        "@etothepii",
        "satisfactory-file-parser",
      ),
    );
  }
  candidates.push(
    path.join(
      __dirname,
      "node_modules",
      "@etothepii",
      "satisfactory-file-parser",
    ),
  );
  candidates.push("@etothepii/satisfactory-file-parser");
  return candidates;
}

function loadParser() {
  const errors = [];
  for (const candidate of parserCandidates()) {
    try {
      const loaded = require(candidate);
      if (loaded && loaded.Parser) {
        let version = null;
        try {
          version = require(path.join(candidate, "package.json")).version;
        } catch (_error) {
          try {
            version = require("@etothepii/satisfactory-file-parser/package.json").version;
          } catch (_ignored) {
            version = null;
          }
        }
        return { Parser: loaded.Parser, parserModule: candidate, parserVersion: version };
      }
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(`Could not load @etothepii/satisfactory-file-parser.\n${errors.join("\n")}`);
}

function cleanNumber(value) {
  if (typeof value !== "number") {
    return value;
  }
  if (!Number.isFinite(value)) {
    return null;
  }
  return Object.is(value, -0) ? 0 : value;
}

function scalarProperty(prop) {
  if (!prop || !Object.prototype.hasOwnProperty.call(prop, "value")) {
    return null;
  }
  const value = prop.value;
  if (typeof value === "bigint") {
    return value.toString();
  }
  if (typeof value === "number") {
    return cleanNumber(value);
  }
  if (typeof value === "boolean" || typeof value === "string") {
    return value;
  }
  return null;
}

function referencePath(prop) {
  const value = prop && Object.prototype.hasOwnProperty.call(prop, "value")
    ? prop.value
    : prop;
  if (!value) {
    return null;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value.pathName === "string") {
    return value.pathName;
  }
  if (typeof value.objectName === "string") {
    return value.objectName;
  }
  return null;
}

function pathLeaf(raw) {
  if (!raw) {
    return null;
  }
  const text = String(raw);
  const leaf = text.split("/").pop() || text;
  return leaf.replace(/\.[^.]+$/, "");
}

function vector(value) {
  if (!value) {
    return null;
  }
  const result = {};
  for (const key of ["x", "y", "z", "w"]) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      result[key] = cleanNumber(value[key]);
    }
  }
  return Object.keys(result).length ? result : null;
}

function transformOf(obj) {
  const transform = obj.transform;
  if (!transform) {
    return null;
  }
  return {
    translation: vector(transform.translation),
    rotation: vector(transform.rotation),
    scale3d: vector(transform.scale3d || transform.scale3D),
  };
}

function compactRef(name, prop) {
  const ref = referencePath(prop);
  return ref ? { [name]: ref } : {};
}

function machineKind(obj) {
  const props = obj.properties || {};
  const typePath = obj.typePath || "";
  if (props.mCurrentRecipe) {
    return "manufacturer";
  }
  if (props.mExtractableResource || /Build_(Miner|OilPump|WaterPump|FrackingExtractor|FrackingSmasher)/.test(typePath)) {
    return "extractor";
  }
  return "production_buildable";
}

function isMachineCandidate(obj) {
  const props = obj.properties || {};
  const typePath = obj.typePath || "";
  return Boolean(
    props.mCurrentRecipe ||
      props.mExtractableResource ||
      PRODUCTION_CLASS_PATTERN.test(typePath),
  );
}

function machineSnapshot(levelName, obj) {
  const props = obj.properties || {};
  const recipePath = referencePath(props.mCurrentRecipe);
  const resourcePath = referencePath(props.mExtractableResource);
  const result = {
    id: obj.instanceName,
    level: levelName,
    typePath: obj.typePath || null,
    type: pathLeaf(obj.typePath),
    kind: machineKind(obj),
    transform: transformOf(obj),
    recipe: recipePath ? { path: recipePath, name: pathLeaf(recipePath) } : null,
    extractableResource: resourcePath
      ? { path: resourcePath, name: pathLeaf(resourcePath) }
      : null,
    clock: {
      currentPotential: scalarProperty(props.mCurrentPotential),
      pendingPotential: scalarProperty(props.mPendingPotential),
      productionBoost: scalarProperty(props.mCurrentProductionBoost),
    },
    state: {
      isProducing: scalarProperty(props.mIsProducing),
      currentProductivityMeasurementDuration: scalarProperty(
        props.mCurrentProductivityMeasurementDuration,
      ),
      currentProductivityMeasurementProduceDuration: scalarProperty(
        props.mCurrentProductivityMeasurementProduceDuration,
      ),
      lastProductivityMeasurementDuration: scalarProperty(
        props.mLastProductivityMeasurementDuration,
      ),
      lastProductivityMeasurementProduceDuration: scalarProperty(
        props.mLastProductivityMeasurementProduceDuration,
      ),
      timeSinceStartStopProducing: scalarProperty(props.mTimeSinceStartStopProducing),
    },
    refs: {
      ...compactRef("powerInfo", props.mPowerInfo),
      ...compactRef("inputInventory", props.mInputInventory),
      ...compactRef("outputInventory", props.mOutputInventory),
      ...compactRef("storageInventory", props.mStorageInventory),
      ...compactRef("inventoryPotential", props.mInventoryPotential),
    },
  };

  for (const section of ["clock", "state", "refs"]) {
    for (const [key, value] of Object.entries(result[section])) {
      if (value === null || value === undefined) {
        delete result[section][key];
      }
    }
  }
  return result;
}

function increment(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function sortedCounts(map) {
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, count]) => ({ name, count }));
}

function stringifyJson(value, pretty) {
  return JSON.stringify(
    value,
    (_key, item) => {
      if (typeof item === "bigint") {
        return item.toString();
      }
      if (typeof item === "number") {
        return cleanNumber(item);
      }
      return item;
    },
    pretty ? 2 : 0,
  );
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }
  if (!options.savePath) {
    throw new Error(usage());
  }

  const savePath = path.resolve(options.savePath);
  const stat = fs.statSync(savePath);
  const { Parser, parserModule, parserVersion } = loadParser();
  const bytes = new Uint8Array(fs.readFileSync(savePath)).buffer;

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => {
    warnings.push(args.join(" "));
  };
  let save;
  try {
    save = Parser.ParseSave(path.basename(savePath, ".sav"), bytes, {
      throwErrors: false,
      onProgressCallback: () => {},
    });
  } finally {
    console.warn = originalWarn;
  }

  const levels = Object.values(save.levels || {});
  const machines = [];
  const countsByType = new Map();
  const countsByKind = new Map();
  let objectCount = 0;
  let objectsWithRecipe = 0;
  let objectsWithTransform = 0;

  for (const level of levels) {
    for (const obj of level.objects || []) {
      objectCount += 1;
      if (obj.transform) {
        objectsWithTransform += 1;
      }
      if (obj.properties && obj.properties.mCurrentRecipe) {
        objectsWithRecipe += 1;
      }
      if (!isMachineCandidate(obj)) {
        continue;
      }
      const snapshot = machineSnapshot(level.name, obj);
      machines.push(snapshot);
      increment(countsByType, snapshot.type || "<unknown>");
      increment(countsByKind, snapshot.kind);
    }
  }

  const output = {
    schemaVersion: 1,
    source: {
      saveName: path.basename(savePath, ".sav"),
      fileName: path.basename(savePath),
      fileSizeBytes: stat.size,
      fileMtime: stat.mtime.toISOString(),
    },
    parser: {
      package: "@etothepii/satisfactory-file-parser",
      version: parserVersion,
      module: parserModule,
      warnings: warnings.length,
      warningSamples: warnings.slice(0, 5),
    },
    header: {
      saveVersion: save.header && save.header.saveVersion,
      buildVersion: save.header && save.header.buildVersion,
      mapName: save.header && save.header.mapName,
      sessionName: save.header && save.header.sessionName,
    },
    counts: {
      levels: levels.length,
      objects: objectCount,
      objectsWithTransform,
      objectsWithCurrentRecipe: objectsWithRecipe,
      machineCandidates: machines.length,
      machineCandidatesByKind: sortedCounts(countsByKind),
      machineCandidatesByType: sortedCounts(countsByType),
    },
  };

  if (!options.summaryOnly) {
    output.machines = machines;
  }

  console.log(stringifyJson(output, options.pretty));
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
}
