// Khronos glTF-Validator pass over every generated GLB.
//
// Usage: node validate.mjs [--manifest <path>] [--report <path>] [--strict] [files...]
//
// Without explicit files it validates every model listed in the asset manifest
// (main models, LODs, collision files, state variants and per-clip animation
// files). Errors always fail (exit 1); with --strict every warning that is not
// in ACCEPTED_WARNINGS fails too.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import validator from "gltf-validator";

// Warnings accepted with a reason; everything else fails under --strict.
const ACCEPTED_WARNINGS = {
  // Blender parents a skinned mesh to its armature node. The pipeline's own
  // GLB inspector verifies that armature roots carry an identity transform,
  // so the (ignored) parent transform cannot change the result.
  NODE_SKINNED_MESH_NON_ROOT: "armature root has an identity transform (checked by glb_inspector)",
};

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");

function parseArgs(argv) {
  const opts = { manifest: null, report: null, strict: false, files: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--manifest") opts.manifest = argv[++i];
    else if (a === "--report") opts.report = argv[++i];
    else if (a === "--strict") opts.strict = true;
    else opts.files.push(a);
  }
  return opts;
}

function manifestFiles(manifest) {
  const out = new Set();
  for (const a of manifest.assets ?? []) {
    if (a.model) out.add(a.model);
    for (const l of a.lod_models ?? []) out.add(l.model);
    if (a.collision_model) out.add(a.collision_model);
    for (const s of Object.values(a.states ?? {})) {
      if (s.model) out.add(s.model);
      for (const l of s.lod_models ?? []) out.add(l);
      if (s.collision_model) out.add(s.collision_model);
    }
    for (const c of Object.values(a.clip_models ?? {})) out.add(c);
  }
  return [...out].sort();
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  let files = opts.files;
  if (files.length === 0) {
    const manifestPath = path.resolve(repo, opts.manifest ?? "assets/manifests/asset_manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    files = manifestFiles(manifest);
    if (files.length === 0) throw new Error(`no models listed in ${manifestPath}`);
  }
  const report = { validator: validator.version(), strict: opts.strict, accepted_warnings: ACCEPTED_WARNINGS,
                   files: [], errors: 0, warnings: 0, unaccepted_warnings: 0 };
  for (const rel of files) {
    const full = path.resolve(repo, rel);
    const bytes = new Uint8Array(await readFile(full));
    const result = await validator.validateBytes(bytes, {
      uri: path.basename(full),
      maxIssues: 0,
      externalResourceFunction: () => Promise.reject(new Error("external resources are not allowed")),
    });
    const issues = result.issues;
    const messages = issues.messages.map((m) => ({ code: m.code, severity: m.severity, message: m.message, pointer: m.pointer }));
    report.files.push({ file: rel, errors: issues.numErrors, warnings: issues.numWarnings, infos: issues.numInfos,
                        hints: issues.numHints, messages: messages.filter((m) => m.severity <= 1) });
    const unaccepted = messages.filter((m) => m.severity === 1 && !(m.code in ACCEPTED_WARNINGS));
    report.errors += issues.numErrors;
    report.warnings += issues.numWarnings;
    report.unaccepted_warnings = (report.unaccepted_warnings ?? 0) + unaccepted.length;
    const tag = issues.numErrors ? "FAIL" : unaccepted.length ? "WARN" : "OK  ";
    console.log(`${tag} ${rel}  errors=${issues.numErrors} warnings=${issues.numWarnings} infos=${issues.numInfos}`);
    for (const m of messages.filter((m) => m.severity <= 1)) {
      console.log(`     ${m.severity === 0 ? "error" : "warning"} ${m.code}: ${m.message} (${m.pointer ?? ""})`);
    }
  }
  const out = path.resolve(repo, opts.report ?? "assets/reports/khronos_validation.json");
  await mkdir(path.dirname(out), { recursive: true });
  await writeFile(out, JSON.stringify(report, null, 2) + "\n");
  console.log(`glTF-Validator ${report.validator}: ${files.length} files, ${report.errors} errors, ` +
              `${report.warnings} warnings (${report.unaccepted_warnings} not accepted)`);
  if (report.errors > 0 || (opts.strict && report.unaccepted_warnings > 0)) process.exit(1);
}

main().catch((err) => {
  console.error(`glTF validation failed: ${err.stack ?? err}`);
  process.exit(1);
});
