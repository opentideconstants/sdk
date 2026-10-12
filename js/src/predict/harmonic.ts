import { angle, utc, yearStart, AstroTable, type AstroRow } from './astro.js';
import { num, str, type JsonObject } from '../json.js';
export const RAD = Math.PI / 180;
const EPSILON = 2 ** -52;
type Term = readonly [AstroRow,number,number,number];
type YearTerm = readonly [number,number,number,number];
export type Event = [number,string,number];
export class Sum {
    readonly table: AstroTable;
    mean: number;
    readonly #terms: Term[] = [];
    readonly #years = new Map<number,readonly [number,YearTerm[]]>();
    constructor(table: AstroTable, constituents: readonly JsonObject[], {amplitude='amplitude_m',phase='phase_deg',mean=0,multiplier=1,shiftHours=0}: {amplitude?:string;phase?:string;mean?:number;multiplier?:number;shiftHours?:number} = {}) {
        this.table=table; this.mean=mean;
        for (const constituent of constituents) {
            const row=table._row(str(constituent,'name') ?? ''); const speed=row.speed_deg_per_hour;
            this.#terms.push([row,speed,multiplier*(num(constituent,amplitude)??0),angle((num(constituent,phase)??0)+speed*shiftHours)]);
        }
    }
    #year(year: number): readonly [number,YearTerm[]] {
        let data=this.#years.get(year);
        if (!data) {const index=this.table._index(year), origin=yearStart(year);const terms=this.#terms.map(([row,speed,amplitude,phase]):YearTerm=>[speed,row.f[index]*amplitude,row.v0u_deg[index]-phase,speed*RAD]);data=[origin,terms];this.#years.set(year,data);}
        return data;
    }
    value(seconds: number, year: number=utc(seconds).getUTCFullYear(), derivative=false): number {
        const [origin,terms]=this.#year(year), delta=(seconds-origin)/3600;let value=0;
        for (const [speed,amplitude,argument,omega] of terms) {const phase=angle(speed*delta+argument)*RAD;value+=derivative?-amplitude*omega*Math.sin(phase):amplitude*Math.cos(phase);}
        return derivative?value:value+this.mean;
    }
    bound(year: number, derivative: boolean): number {let bound=0;for(const [,amplitude,,omega] of this.#year(year)[1])bound+=Math.abs(amplitude)*omega**(derivative?2:1);return bound;}
    error(year: number,a: number,b: number,derivative: boolean): number {const [origin,terms]=this.#year(year),deltaMax=Math.max(Math.abs(a-origin),Math.abs(b-origin))/3600;let sum=0;for(const [,amplitude,,omega] of terms)sum+=Math.abs(amplitude)*(derivative?omega:1)*(Math.abs(omega*deltaMax)+2*Math.PI);return 4*EPSILON*sum;}
}
function survivor(cluster: Event[], slack: boolean): Event | null {
    if (cluster.length%2===0)return null;
    if(slack)return cluster[2*Math.floor((cluster.length-1)/4)];
    const wanted=cluster[0][1];let best=cluster[0];
    for(const c of cluster)if(c[1]===wanted && (wanted==='high'?c[2]>best[2]||c[2]===best[2]&&c[0]<best[0]:c[2]<best[2]||c[2]===best[2]&&c[0]<best[0]))best=c;
    return best;
}
export function events(total: Sum,start: number,stop: number,slack=false): Event[] {
    if(start===stop)return [];
    const first=Math.floor(start/360)*360-3600,last=Math.ceil((stop+3600-first)/360)*360+first;
    for(let point=first;point<=last;point+=360)total.table._index(utc(point).getUTCFullYear());
    const derivative=!slack,roots:Event[]=[];
    for(let left=first;left<last;left+=360) {
        const year=utc(left).getUTCFullYear(),bound=total.bound(year,derivative);
        const value=(t:number)=>total.value(t,year,derivative);
        const subdivide=(a:number,b:number,fa:number,fb:number,depth:number):void=>{
            const margin=bound*((b-a)/3600)*(1+1e-9)+2*total.error(year,a,b,derivative)+1e-12*Math.max(1,bound);
            if(Math.abs(fa)+Math.abs(fb)>margin)return;
            if(depth<9){const middle=(a+b)/2,fm=value(middle);subdivide(a,middle,fa,fm,depth+1);subdivide(middle,b,fm,fb,depth+1);return;}
            const falling=fa>0&&fb<=0,rising=fa<0&&fb>=0;if(!falling&&!rising)return;
            while(b-a>0.01){const middle=(a+b)/2,fm=value(middle);if(falling&&fm>0||rising&&fm<0)a=middle;else b=middle;}
            const root=(a+b)/2,kind=slack?(falling?'slack_before_ebb':'slack_before_flood'):(falling?'high':'low');roots.push([root,kind,slack?0:total.value(root,year)]);
        };
        subdivide(left,left+360,value(left),value(left+360),0);
    }
    for(let year=utc(first).getUTCFullYear()+1;year<=utc(last).getUTCFullYear();year++){
        const boundary=yearStart(year);if(!(first<boundary&&boundary<last))continue;
        const old=total.value(boundary,year-1,derivative),fresh=total.value(boundary,year,derivative);if(old===0||fresh===0||(old>0)===(fresh>0))continue;
        const lefts=roots.filter(c=>c[0]<=boundary),rights=roots.filter(c=>c[0]>boundary),left=lefts[lefts.length-1],right=rights[0];
        if(left&&right&&right[0]-left[0]<3600){const loser=slack?right:survivor([left,right,left],false)===left?right:left;roots.splice(roots.indexOf(loser),1);}
        else {const kind=slack?(fresh>0?'slack_before_flood':'slack_before_ebb'):(old>0?'high':'low');roots.push([boundary,kind,slack?0:total.value(boundary,year)]);}
        roots.sort((a,b)=>a[0]-b[0]);
    }
    const kept:Event[]=[];let cluster:Event[]=[];
    for(const candidate of roots){if(cluster.length&&candidate[0]-cluster[cluster.length-1][0]>=1){const hit=survivor(cluster,slack);if(hit)kept.push(hit);cluster=[];}cluster.push(candidate);}
    if(cluster.length){const hit=survivor(cluster,slack);if(hit)kept.push(hit);}
    return kept.filter(c=>start<=Math.floor(c[0]+0.5)&&Math.floor(c[0]+0.5)<stop);
}
