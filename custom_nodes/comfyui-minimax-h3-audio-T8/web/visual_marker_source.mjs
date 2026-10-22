// Resolve links in the node's own graph, never a different graph with reused IDs.
export function directSource(node,name,fallbackGraph) {
    const graph=node.graph??fallbackGraph, pin=node.inputs?.find(p=>p.name===name);
    if (!graph || pin?.link==null) return null;
    const link=graph.links?.get?.(pin.link)??graph.links?.[pin.link];
    const origin=link && graph.getNodeById?.(link.origin_id);
    return origin?{node:origin,graph,link}:null;
}

export function imageSource(node,fallbackGraph) {
    let current=node, name="image";
    const visited=new Set();
    while (current) {
        if (visited.has(current)) return null; visited.add(current);
        const source=directSource(current,name,fallbackGraph);
        if (!source) return null;
        if (source.node.type==="LoadImage") {
            if (source.node.inputs?.some(p=>p.name==="image" && p.link!=null)) return null;
            const value=source.node.widgets?.find(w=>w.name==="image")?.value;
            if (typeof value!=="string" || !value) return null;
            const annotation=/ \[(input|output|temp)\]$/.exec(value);
            const path=annotation?value.slice(0,annotation.index):value;
            const parts=path.replaceAll("\\","/").split("/");
            return {filename:parts.pop(),subfolder:parts.join("/"),type:annotation?.[1]??"input"};
        }
        if (source.node.type!=="Reroute" || source.node.inputs?.length!==1) return null;
        current=source.node; name=current.inputs[0].name; fallbackGraph=source.graph;
    }
    return null;
}
