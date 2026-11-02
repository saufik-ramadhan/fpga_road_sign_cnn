/* Architectural illustration shared by the road-sign and MNIST debuggers. */
function renderNetworkDiagram(container, contract, parameters) {
  const ns = 'http://www.w3.org/2000/svg';
  const side = contract.image_size, conv = side - 2, pool = conv / 2;
  const filters = contract.filters, classes = contract.classes.length;
  const featureCount = parameters.fc_weight[0].length;
  const accent = 'var(--nn-accent, #176448)';
  function node(tag, attrs = {}, content) {
    const item = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, value]) => item.setAttribute(key, value));
    if (content !== undefined) item.textContent = content;
    return item;
  }
  const svg = node('svg', {viewBox: '0 0 1240 385', role: 'img',
    'aria-labelledby': 'nn-title nn-description', style: 'width:100%;min-width:1000px;display:block;font-family:Segoe UI,Arial,sans-serif'});
  svg.append(node('title', {id: 'nn-title'}, `Arsitektur CNN ${contract.dataset || 'rambu'} ${side}×${side}, ${classes} kelas`));
  svg.append(node('desc', {id: 'nn-description'},
    `Input ${side}×${side}×1, convolution VALID 3×3 dengan ${filters} filter, ReLU dan rescale, max pooling 2×2, flatten CHW ${featureCount} fitur, fully connected ${classes} skor dan argmax. Neuron dan koneksi ditampilkan secara ringkas sebagai ilustrasi.`));
  const style = node('style');
  style.textContent = '.nn-highlight{fill:transparent;stroke:transparent;stroke-width:1.5}.nn-stage.nn-current .nn-highlight{fill:#f2f6f0;stroke:var(--nn-accent,#176448)}.nn-text{fill:#243c39;font-size:14px}.nn-small{fill:#687c73;font-size:12px}.nn-heading{fill:#687c73;font-size:11px;letter-spacing:1.5px}';
  svg.append(style);
  const defs = node('defs');
  const marker = node('marker', {id: 'nn-arrow', viewBox:'0 0 10 10', refX:9,refY:5,
    markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
  marker.append(node('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#92a99c'}));
  defs.append(marker);svg.append(defs);
  function text(parent, x, y, content, cls = 'nn-text', anchor='middle') {
    parent.append(node('text',{x,y,'text-anchor':anchor,class:cls},content));
  }
  function line(parent,x1,y1,x2,y2,attrs={}) {
    parent.append(node('line',{x1,y1,x2,y2,stroke:'#92a99c','stroke-width':1.5,...attrs}));
  }
  text(svg, 425, 20, 'EKSTRAKSI FITUR', 'nn-heading');
  line(svg,170,32,665,32,{stroke:'#d6e0d6'});
  text(svg, 955, 20, 'KLASIFIKASI', 'nn-heading');
  line(svg,686,32,1223,32,{stroke:'#d6e0d6'});
  const centers = [78,245,410,575,740,945,1150];
  const labels = ['Input','Convolution','ReLU + rescale','Max pooling','Flatten CHW','Fully connected','Argmax'];
  const shapes = [`${side} × ${side} × 1`,`${conv} × ${conv} × ${filters}`,`${conv} × ${conv} × ${filters}`,
    `${pool} × ${pool} × ${filters}`,`${featureCount.toLocaleString('id-ID')} fitur`,`${classes} skor`,`${classes} kelas`];
  const details = ['Pixel uint8','Kernel 3×3 · VALID','Aktivasi 0–127','2×2 · stride 2','Urutan C → H → W','Bobot + bias','Indeks skor terbesar'];
  const groups = centers.map((x,i)=>{
    const g=node('g',{class:'nn-stage','data-stage':i});
    g.append(node('rect',{x:x-(i===5?84:73),y:44,width:i===5?168:146,height:314,rx:12,class:'nn-highlight'}));
    text(g,x,68,labels[i]);text(g,x,320,shapes[i]);text(g,x,342,details[i],'nn-small');
    svg.append(g);return g;
  });
  for(let i=0;i<4;i++) line(svg,centers[i]+66,190,centers[i+1]-68,190,{'marker-end':'url(#nn-arrow)'});
  line(svg,centers[5]+77,190,centers[6]-67,190,{'marker-end':'url(#nn-arrow)'});
  // A schematic pixel plane. Cell shades illustrate a grid, not the input tensor.
  for(let y=0;y<7;y++) for(let x=0;x<7;x++) groups[0].append(node('rect',{
    x:29+x*14,y:137+y*14,width:13,height:13,rx:1,
    fill:(x+y)%3===0?'#8eae9a':'#e5ece2',stroke:'#fff','stroke-width':.5}));
  function planes(group,cx,width) {
    for(let layer=3;layer>=0;layer--) group.append(node('rect',{
      x:cx-width/2+layer*6-8,y:190-width/2-layer*7+8,width,height:width,rx:3,
      fill:layer%2?'#d9e7df':'#f1f6ef',stroke:'#7e9f8c','stroke-width':1.4}));
    text(group,cx,278,`${filters} feature maps`,'nn-small');
  }
  planes(groups[1],245,91);planes(groups[2],410,91);planes(groups[3],575,62);
  // Only seven representative inputs are drawn; the actual feature count is below.
  const featureYs=[120,143,166,190,214,237,260];
  const scoreYs=Array.from({length:classes},(_,i)=>104+i*174/(classes-1));
  const edges=node('g',{'aria-hidden':'true'});
  for(const y1 of featureYs) for(const y2 of scoreYs) line(edges,751,y1,914,y2,
    {stroke:'#bacabd','stroke-width':.8,opacity:.48});
  svg.insertBefore(edges,groups[4]);
  featureYs.forEach(y=>groups[4].append(node('circle',{cx:740,cy:y,r:10,fill:'#ecf2e7',stroke:accent,'stroke-width':1.5})));
  text(groups[4],769,194,'…','nn-small');
  scoreYs.forEach((y,i)=>{
    groups[5].append(node('circle',{cx:925,cy:y,r:10,fill:'#e7eef4',stroke:accent,'stroke-width':1.5}));
    text(groups[5],946,y+4,`Skor ${i}`,'nn-small','start');
  });
  groups[6].append(node('rect',{x:1100,y:151,width:100,height:78,rx:12,fill:'#edf2e9',stroke:accent,'stroke-width':1.5}));
  text(groups[6],1150,181,'Kelas');text(groups[6],1150,207,`0–${classes-1}`);
  text(svg,740,379,'Ilustrasi koneksi FC: setiap fitur terhubung ke setiap skor kelas.','nn-small');
  container.replaceChildren(svg);
}

function highlightNetworkStage(container, stage, hasResult) {
  container.querySelectorAll('[data-stage]').forEach(group=>{
    group.classList.toggle('nn-current', Boolean(hasResult) && Number(group.dataset.stage)===stage);
  });
}
