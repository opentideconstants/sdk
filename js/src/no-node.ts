/**
 * @internal What "#node" (package.json "imports") gives where the "node" condition does not apply, as in a browser
 * bundle: no Node runtime, so a bundler never pulls node.ts and its node: modules into a browser build (CR T64).
 */
import type { NodeMod } from "./node-api.js";

export const nodeApi: NodeMod | null = null;
