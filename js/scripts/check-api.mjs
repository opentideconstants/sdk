// The API manifest check for the TypeScript SDK (spec 7.1): compare conformance/api.json with the
// declarations in the emitted dist/index.d.ts, read with the TypeScript compiler API. A missing or an
// extra name fails. Run after `npm run build`:  node scripts/check-api.mjs [--no-self-test]
//
// Naming (api.json "naming.typescript"): methods, predicates (is_x -> isX getter), attributes and options
// are camelCase; fields keep snake_case. Enum names become PascalCase type aliases (an enum whose name is
// also an object name gets the suffix "Name": qc_flag -> QcFlagName). Error classes keep their names, and
// an error class declares exactly its manifest fields (cause is Error's own). A declaration file with a
// type error (an unresolved type) fails, because the checks below would read such a type as any.
//
// After the check the script runs its own mutation self-test: each mutation of the declaration files must
// be caught.
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const root = new URL("..", import.meta.url);
const api = JSON.parse(readFileSync(new URL("../conformance/api.json", root), "utf8"));
const distDir = fileURLToPath(new URL("dist", root));

const camel = (s) => s.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
const pascal = (s) => camel(s).replace(/^./, (c) => c.toUpperCase());
const forTs = (m) => !m.languages || m.languages.includes("typescript");
const tsName = (m) => (m.kind === "field" ? m.name : camel(m.name));
const filterNames = api.filters.map((f) => camel(f.name));
const FILTER_OPS = new Set(["stations", "iter_stations", "search", "near", "nearest"]);

/** The problems of the declarations in dir/index.d.ts (and the runtime module, if given). */
function check(dir, runtime) {
    const dts = join(dir, "index.d.ts");
    const program = ts.createProgram([dts], { strict: true, skipLibCheck: false, noEmit: true, types: ["node"] });
    const checker = program.getTypeChecker();
    const problems = [];
    const fail = (msg) => problems.push(msg);
    let checked = 0;

    // an unresolved type would read as any below, so a type error in the declarations is a failure
    for (const d of ts.getPreEmitDiagnostics(program)) {
        if (d.category !== ts.DiagnosticCategory.Error) continue;
        const where = d.file ? `${d.file.fileName.slice(dir.length + 1)}:${d.file.getLineAndCharacterOfPosition(d.start).line + 1}` : "";
        fail(`type error in the declarations ${where}: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`);
    }

    const sf = program.getSourceFile(dts);
    const moduleSym = sf && checker.getSymbolAtLocation(sf);
    if (!moduleSym) return { problems: [...problems, `cannot read ${dts}`], checked };
    const exportsByName = new Map(checker.getExportsOfModule(moduleSym).map((s) => [s.getName(), s]));
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

    function optionKeys(param) {
        const t = checker.getTypeAtLocation(param);
        return new Set(checker.getPropertiesOfType(checker.getNonNullableType(t)).map((s) => s.getName()));
    }

    function isPromise(node) {
        const sig = checker.getSignatureFromDeclaration(node);
        const rt = sig && checker.getReturnTypeOfSignature(sig);
        return rt?.getSymbol()?.getName() === "Promise";
    }

    /** The class declarations a class extends, nearest first. */
    function baseChain(sym) {
        const out = [];
        let t = checker.getDeclaredTypeOfSymbol(sym);
        for (let i = 0; i < 50; i++) {
            const bases = t.isClassOrInterface() ? checker.getBaseTypes(t) : [];
            if (!bases.length) break;
            t = bases[0];
            const s = t.getSymbol();
            if (!s) break;
            out.push(s.getName());
        }
        return out;
    }

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
            if (m.kind === "method" && a.node && isMethod) {
                if (Boolean(m.typescript_async) !== isPromise(a.node)) fail(`${objName}.${name}: ${m.typescript_async ? "must" : "must not"} return a Promise`);
                const args = m.args ?? [];
                const opt = args.filter((x) => !x.positional || name === "download").map((x) => camel(x.name));
                if (FILTER_OPS.has(m.name)) opt.push(...filterNames);
                const positional = args.filter((x) => x.positional && name !== "download").length;
                const params = a.node.parameters ?? [];
                if (opt.length) {
                    const p = params[params.length - 1];
                    if (!p || params.length !== positional + 1) fail(`${objName}.${name}: ${params.length} parameters, expected ${positional} and an options object`);
                    if (!p) continue;
                    const keys = optionKeys(p);
                    for (const k of opt) if (!keys.has(k)) fail(`${objName}.${name}: options miss ${k}`);
                    for (const k of keys) if (!opt.includes(k)) fail(`${objName}.${name}: options have extra ${k}`);
                } else if (params.length !== positional) {
                    fail(`${objName}.${name}: ${params.length} parameters, expected ${positional} (the manifest lists no options)`);
                }
            }
        }
    }

    // errors: every class is exported, extends the base class directly, and declares exactly its fields
    const base = api.error_base_class.typescript;
    if (!exportsByName.has(base)) fail(`error base class ${base} is not exported`);
    const errorClasses = api.errors.filter((e) => e.class && e.languages.includes("typescript"));
    for (const e of errorClasses) {
        const sym = exportsByName.get(e.class);
        if (!sym) { fail(`error ${e.code}: class ${e.class} is not exported`); continue; }
        const decl = resolve(sym).declarations?.find(ts.isClassDeclaration);
        const ext = decl?.heritageClauses?.find((h) => h.token === ts.SyntaxKind.ExtendsKeyword)?.types[0]?.expression.getText();
        if (ext !== base) fail(`${e.class}: extends ${ext}, not ${base}`);
        const own = [...(publicMembers(resolve(sym))?.keys() ?? [])];
        const want = e.fields.filter((f) => f !== "cause");
        for (const f of want) if (!own.includes(f)) fail(`${e.class}: missing field ${f}`);
        for (const f of own) if (!want.includes(f)) fail(`${e.class}: extra field ${f}`);
        checked++;
    }
    for (const [name, sym] of exportsByName) {
        const r = resolve(sym);
        if (!(r.flags & ts.SymbolFlags.Class) || name === base) continue;
        if (baseChain(r).includes(base) && !errorClasses.some((e) => e.class === name)) fail(`extra error class ${name}`);
    }
    // the code union matches the error codes for TypeScript
    const codes = errorClasses.map((e) => e.code).sort();
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
    for (const [name, c] of Object.entries(api.constants)) {
        if (name === "c_only") continue;
        if (!exportsByName.has(name)) { fail(`constant ${name} is not exported`); continue; }
        if (runtime && JSON.stringify(runtime[name]) !== JSON.stringify(c.value)) fail(`constant ${name} is ${JSON.stringify(runtime[name])}, expected ${JSON.stringify(c.value)}`);
        checked++;
    }
    // reserved phase 2 names must not be exposed yet: no reserved object, no reserved operation on any
    // exported class or interface, no reserved error class
    for (const op of api.reserved_phase2.operations) {
        if (op.object !== "Client" && exportsByName.has(op.object)) fail(`phase 2 object ${op.object} is exposed`);
        if (exportsByName.has(camel(op.name))) fail(`phase 2 name ${camel(op.name)} is exported`);
        for (const [name, sym] of exportsByName) {
            if (publicMembers(resolve(sym))?.has(camel(op.name))) fail(`phase 2 name ${name}.${camel(op.name)} is exposed`);
        }
    }
    for (const e of api.reserved_phase2.errors ?? []) if (exportsByName.has(e.class)) fail(`phase 2 error class ${e.class} is exported`);
    return { problems, checked };
}

// ---------------------------------------------------------------- self-test

const sub = (file, from, to) => ({ file, from, to });
const MUTATIONS = [
    // [name, edits of the declaration files, a substring of the problem it must cause]
    ["unresolved-type", [sub("types.d.ts", "readonly station_id: string;", "readonly station_id: Missing;")], "Cannot find name 'Missing'"],
    ["extra-error-class-via-subclass", [
        sub("errors.d.ts", "export declare class FileExistsError", "export declare class QuotaError extends CacheError {\n}\nexport declare class FileExistsError"),
        sub("index.d.ts", "CacheError, FileExistsError,", "CacheError, QuotaError, FileExistsError,")], "extra error class QuotaError"],
    ["error-extra-field", [sub("errors.d.ts", "readonly removed: readonly string[];", "readonly removed: readonly string[];\n    readonly stationId: string;")],
        "CacheError: extra field stationId"],
    ["error-missing-field", [sub("errors.d.ts", "readonly removed: readonly string[];", "")], "CacheError: missing field removed"],
    ["extra-options-where-none", [sub("client.d.ts", "close(): void;", "close(options?: { force?: boolean }): void;")],
        "Client.close: 1 parameters, expected 0"],
    ["extra-option", [sub("types.d.ts", "export interface PruneOptions {", "export interface PruneOptions {\n    dryRun?: boolean;")],
        "Client.prune: options have extra dryRun"],
    ["reserved-op", [sub("release.d.ts", "export declare class Release {", "export declare class Release {\n    heights(): void;")],
        "phase 2 name Release.heights is exposed"],
    ["reserved-error-class", [
        sub("errors.d.ts", "export declare class FileExistsError", "export declare class UnsupportedConventionError extends OpenTideConstantsError {\n}\nexport declare class FileExistsError"),
        sub("index.d.ts", "CacheError, FileExistsError,", "CacheError, UnsupportedConventionError, FileExistsError,")],
        "phase 2 error class UnsupportedConventionError is exported"],
    ["enum-extra-value", [sub("types.d.ts", "\"webcaltides\" | \"linz\"", "\"webcaltides\" | \"foo\" | \"linz\"")], "enum AliasSystem"],
    ["no-SUPPORTED_FORMAT_VERSION", [sub("index.d.ts", "SUPPORTED_FORMAT_VERSION, ", "")], "constant SUPPORTED_FORMAT_VERSION is not exported"],
    ["filter-dropped", [sub("types.d.ts", "sourceType?: SourceType | null;", "sourceKind?: SourceType | null;")], "options miss sourceType"],
];

function selfTest(baseProblems) {
    const out = [];
    for (const [name, edits, expect] of MUTATIONS) {
        const dir = mkdtempSync(join(tmpdir(), "otc-check-api-"));
        try {
            cpSync(distDir, dir, { recursive: true });
            for (const e of edits) {
                const p = join(dir, e.file);
                const text = readFileSync(p, "utf8");
                if (!text.includes(e.from)) throw new Error(`${e.file} has no ${JSON.stringify(e.from)}`);
                writeFileSync(p, text.replace(e.from, e.to));
            }
            const got = check(dir, null).problems.map((p) => p.replace(dir, "<dist>"));
            const fresh = got.filter((p) => !baseProblems.includes(p));
            if (!fresh.some((p) => p.includes(expect))) out.push(`${name}: not caught (wanted a problem with ${JSON.stringify(expect)}; new problems ${JSON.stringify(fresh)})`);
        } catch (e) {
            out.push(`${name}: the mutation or the check failed: ${e.message}`);
        } finally {
            rmSync(dir, { recursive: true, force: true });
        }
    }
    return out;
}

export { MUTATIONS };

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    const runtime = await import(new URL("dist/index.js", root).href);
    const { problems, checked } = check(distDir, runtime);
    let rc = 0;
    if (problems.length) {
        console.error(`API manifest check FAILED (${problems.length} problems):`);
        for (const p of problems) console.error(`  - ${p}`);
        rc = 1;
    } else {
        console.log(`API manifest check OK: ${checked} names compared with conformance/api.json (suite ${api.suite_version})`);
    }
    if (!process.argv.includes("--no-self-test")) {
        const bad = selfTest(problems);
        for (const b of bad) console.error(`SELF-TEST ${b}`);
        console.log(`self-test: ${MUTATIONS.length - bad.length} of ${MUTATIONS.length} mutations caught`);
        if (bad.length) rc = 1;
    }
    process.exit(rc);
}
