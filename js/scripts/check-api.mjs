// The API manifest check for the TypeScript SDK (spec 7.1): compare conformance/api.json with the
// declarations in the emitted dist/index.d.ts, read with the TypeScript compiler API. A missing or an
// extra name fails. Run after `npm run build`:  node scripts/check-api.mjs
//
// Naming (api.json "naming.typescript"): methods, predicates (is_x -> isX getter), attributes and options
// are camelCase; fields keep snake_case. Enum names become PascalCase type aliases (an enum whose name is
// also an object name gets the suffix "Name": qc_flag -> QcFlagName). Error classes keep their names.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = new URL("..", import.meta.url);
const api = JSON.parse(readFileSync(new URL("../conformance/api.json", root), "utf8"));
const dts = fileURLToPath(new URL("dist/index.d.ts", root));

const camel = (s) => s.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
const pascal = (s) => camel(s).replace(/^./, (c) => c.toUpperCase());
const forTs = (m) => !m.languages || m.languages.includes("typescript");
const tsName = (m) => (m.kind === "field" ? m.name : camel(m.name));

const program = ts.createProgram([dts], { strict: true, skipLibCheck: true, types: ["node"] });
const checker = program.getTypeChecker();
const sf = program.getSourceFile(dts);
const moduleSym = checker.getSymbolAtLocation(sf);
const exportsByName = new Map(checker.getExportsOfModule(moduleSym).map((s) => [s.getName(), s]));

const problems = [];
const fail = (msg) => problems.push(msg);
const resolve = (sym) => (sym.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(sym) : sym);

function publicMembers(sym) {
    const decl = sym.declarations?.find((d) => ts.isClassDeclaration(d) || ts.isInterfaceDeclaration(d));
    if (!decl) return null;
    const out = new Map();
    const add = (m, isStatic) => {
        if (ts.isConstructorDeclaration(m) || ts.isIndexSignatureDeclaration(m)) return;
        if (!m.name || ts.isComputedPropertyName(m.name) || ts.isPrivateIdentifier(m.name)) return;
        const mods = ts.canHaveModifiers(m) ? ts.getModifiers(m) ?? [] : [];
        if (mods.some((x) => x.kind === ts.SyntaxKind.PrivateKeyword || x.kind === ts.SyntaxKind.ProtectedKeyword)) return;
        out.set(m.name.getText(), { node: m, isStatic });
    };
    for (const m of decl.members) add(m, (ts.getModifiers?.(m) ?? []).some((x) => x.kind === ts.SyntaxKind.StaticKeyword));
    // inherited interface members (extends) count too
    if (ts.isInterfaceDeclaration(decl)) {
        for (const p of checker.getPropertiesOfType(checker.getDeclaredTypeOfSymbol(sym))) if (!out.has(p.getName())) out.set(p.getName(), { node: null, isStatic: false });
    }
    return out;
}

function optionKeys(node) {
    // the last parameter's object type: its property names
    const params = node.parameters ?? [];
    const p = params[params.length - 1];
    if (!p) return null;
    const t = checker.getTypeAtLocation(p);
    return new Set(checker.getPropertiesOfType(checker.getNonNullableType(t)).map((s) => s.getName()));
}

function isPromise(node) {
    const sig = checker.getSignatureFromDeclaration(node);
    const rt = sig && checker.getReturnTypeOfSignature(sig);
    return rt?.getSymbol()?.getName() === "Promise";
}

const filterNames = api.filters.map((f) => camel(f.name));
const FILTER_OPS = new Set(["stations", "iter_stations", "search", "near", "nearest"]);
let checked = 0;

for (const [objName, obj] of Object.entries(api.objects)) {
    const members = obj.members.filter(forTs);
    const expected = new Map(members.map((m) => [tsName(m), m]));
    if (objName === "Client") {
        for (const m of api.objects.Release.members) if (m.forwarded_to_client && forTs(m)) expected.set(tsName(m), m);
    }
    const sym = exportsByName.get(objName === "Client" ? "OpenTideConstants" : objName);
    if (!sym) { fail(`${objName}: not exported`); continue; }
    const actual = publicMembers(resolve(sym));
    if (!actual) { fail(`${objName}: not a class or interface`); continue; }
    for (const name of expected.keys()) if (!actual.has(name)) fail(`${objName}: missing ${name}`);
    for (const name of actual.keys()) if (!expected.has(name)) fail(`${objName}: extra ${name}`);
    for (const [name, m] of expected) {
        const a = actual.get(name);
        if (!a) continue;
        checked++;
        if (m.static && !a.isStatic) fail(`${objName}.${name}: must be static`);
        const isMethod = a.node && (ts.isMethodDeclaration(a.node) || ts.isMethodSignature(a.node));
        if (m.kind === "method" && a.node && !isMethod) fail(`${objName}.${name}: must be a method`);
        if ((m.kind === "attribute" || m.kind === "predicate") && a.node && isMethod) fail(`${objName}.${name}: must be a getter or property, not a method`);
        if (m.kind === "method" && a.node) {
            if (Boolean(m.typescript_async) !== isPromise(a.node)) fail(`${objName}.${name}: ${m.typescript_async ? "must" : "must not"} return a Promise`);
            const opt = (m.args ?? []).filter((x) => !x.positional || name === "download").map((x) => camel(x.name));
            if (FILTER_OPS.has(m.name)) opt.push(...filterNames);
            if (opt.length) {
                const keys = optionKeys(a.node);
                if (!keys) fail(`${objName}.${name}: has no options parameter`);
                else {
                    for (const k of opt) if (!keys.has(k)) fail(`${objName}.${name}: options miss ${k}`);
                    for (const k of keys) if (!opt.includes(k)) fail(`${objName}.${name}: options have extra ${k}`);
                }
            }
        }
    }
}

// errors: every class is exported and extends the base class directly
const base = api.error_base_class.typescript;
if (!exportsByName.has(base)) fail(`error base class ${base} is not exported`);
const errorClasses = api.errors.filter((e) => e.class && e.languages.includes("typescript"));
for (const e of errorClasses) {
    const sym = exportsByName.get(e.class);
    if (!sym) { fail(`error ${e.code}: class ${e.class} is not exported`); continue; }
    const decl = resolve(sym).declarations?.find(ts.isClassDeclaration);
    const ext = decl?.heritageClauses?.find((h) => h.token === ts.SyntaxKind.ExtendsKeyword)?.types[0]?.expression.getText();
    if (ext !== base) fail(`${e.class}: extends ${ext}, not ${base}`);
    for (const f of e.fields) if (f !== "cause" && !publicMembers(resolve(sym))?.has(f)) fail(`${e.class}: missing field ${f}`);
    checked++;
}
for (const [name, sym] of exportsByName) {
    const decl = resolve(sym).declarations?.find(ts.isClassDeclaration);
    const ext = decl?.heritageClauses?.find((h) => h.token === ts.SyntaxKind.ExtendsKeyword)?.types[0]?.expression.getText();
    if (ext === base && !errorClasses.some((e) => e.class === name)) fail(`extra error class ${name}`);
}
// the code union matches the error codes for TypeScript
const codes = api.errors.filter((e) => e.class && e.languages.includes("typescript")).map((e) => e.code).sort();
const codeSym = exportsByName.get("ErrorCode");
const codeUnion = codeSym && checker.getDeclaredTypeOfSymbol(resolve(codeSym));
const got = codeUnion?.isUnion() ? codeUnion.types.map((t) => t.value).sort() : [];
if (JSON.stringify(got) !== JSON.stringify(codes)) fail(`ErrorCode is ${JSON.stringify(got)}, expected ${JSON.stringify(codes)}`);

// enums: string-literal union type aliases
for (const [name, values] of Object.entries(api.enums)) {
    const alias = api.objects[pascal(name)] ? `${pascal(name)}Name` : pascal(name);
    const sym = exportsByName.get(alias);
    if (!sym) { fail(`enum ${name}: type ${alias} is not exported`); continue; }
    const t = checker.getDeclaredTypeOfSymbol(resolve(sym));
    const members = (t.isUnion() ? t.types : [t]).map((x) => x.value).sort();
    if (JSON.stringify(members) !== JSON.stringify([...values].sort())) fail(`enum ${alias}: ${JSON.stringify(members)} != ${JSON.stringify([...values].sort())}`);
    checked++;
}

// constants: exported, with the manifest's values
const runtime = await import(new URL("dist/index.js", root).href);
for (const [name, c] of Object.entries(api.constants)) {
    if (name === "c_only") continue;
    if (!exportsByName.has(name)) { fail(`constant ${name} is not exported`); continue; }
    if (JSON.stringify(runtime[name]) !== JSON.stringify(c.value)) fail(`constant ${name} is ${JSON.stringify(runtime[name])}, expected ${JSON.stringify(c.value)}`);
    checked++;
}
// reserved phase 2 names must not be exposed yet
for (const op of api.reserved_phase2.operations) {
    const owner = exportsByName.get(op.object === "Client" ? "OpenTideConstants" : op.object);
    if (owner && publicMembers(resolve(owner))?.has(camel(op.name))) fail(`phase 2 name ${op.object}.${camel(op.name)} is exposed`);
}

if (problems.length) {
    console.error(`API manifest check FAILED (${problems.length} problems):`);
    for (const p of problems) console.error(`  - ${p}`);
    process.exit(1);
}
console.log(`API manifest check OK: ${checked} names compared with conformance/api.json (suite ${api.suite_version})`);
