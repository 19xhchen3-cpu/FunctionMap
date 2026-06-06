/**
 * FunctionMap - 前端交互逻辑
 *
 * 职责:
 * - 管理左侧函数列表(sidebar)
 * - 点击函数 → 获取子图 → 渲染局部调用关系
 * - 点击参数 → 着色参数流向连线
 */

// ===== 全局状态 =====
let currentGraphId = null;
let network = null;
let nodesDataset = null;
let edgesDataset = null;
let sidebarData = [];         // 函数列表数据（按文件分组）
let currentFuncId = null;     // 当前选中的函数

// ===== 页面加载就绪 =====
document.addEventListener('DOMContentLoaded', function() {
    // 双击地址栏打开文件夹选择器
    document.getElementById('folderInput').addEventListener('dblclick', browseFolder);

    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            toggleSearch();
        }
        if (e.key === 'Escape') {
            closeDetail();
            hideSearch();
        }
    });
});

// ===== 文件夹选择 =====
async function browseFolder() {
    try {
        setStatus('打开文件夹选择器...');
        const resp = await fetch('/api/browse-folder');
        const data = await resp.json();
        if (data.path) {
            document.getElementById('folderInput').value = data.path;
            setStatus('就绪');
        } else if (data.error) {
            setStatus('文件夹选择器不可用: ' + data.error);
        }
    } catch (error) {
        console.warn('文件夹选择器不可用:', error);
        setStatus('文件夹选择器不可用，请手动输入路径');
    }
}

// ===== 扫描流程 =====
async function startScan() {
    const folderPath = document.getElementById('folderInput').value.trim();
    if (!folderPath) {
        alert('请先输入代码文件夹路径');
        return;
    }

    const scanBtn = document.getElementById('scanBtn');
    const resetBtn = document.getElementById('resetBtn');
    const progressRow = document.getElementById('progressRow');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const statsRow = document.getElementById('statsRow');
    const statsText = document.getElementById('statsText');

    scanBtn.disabled = true;
    progressRow.style.display = 'flex';
    progressFill.style.width = '20%';
    progressText.textContent = '扫描文件中...';
    setStatus('正在扫描...');

    try {
        // Step 1: 扫描
        const scanResp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath }),
        });

        if (!scanResp.ok) {
            const errData = await scanResp.json();
            throw new Error(errData.detail || `HTTP ${scanResp.status}`);
        }

        progressFill.style.width = '50%';
        progressText.textContent = '加载函数列表中...';

        const scanData = await scanResp.json();
        currentGraphId = scanData.graph_id;

        // Step 2: 获取函数列表（不加载全量图）
        const funcResp = await fetch(`/api/graph/${currentGraphId}/functions`);
        if (!funcResp.ok) throw new Error('获取函数列表失败');

        progressFill.style.width = '70%';
        progressText.textContent = '构建函数列表...';

        sidebarData = await funcResp.json();
        populateSidebar(sidebarData);

        // Step 3: 显示sidebar，清空图区域
        document.getElementById('leftSidebar').classList.remove('hidden');
        document.getElementById('graphPlaceholder').style.display = 'flex';
        document.getElementById('graphPlaceholder').querySelector('h2').textContent =
            '👆 从左侧列表选择一个函数';
        document.getElementById('graphPlaceholder').querySelector('p').textContent =
            '点击函数名查看其调用关系子图（±3层）';
        document.getElementById('graphArea').style.display = 'none';

        // 更新UI
        progressFill.style.width = '100%';
        progressText.textContent = '完成!';

        statsRow.style.display = 'flex';
        statsText.innerHTML = `✅ ${scanData.message}`;
        resetBtn.disabled = false;

        const totalFuncs = sidebarData.reduce((sum, g) => sum + g.functions.length, 0);
        setStatus(`就绪 | ${totalFuncs} 个函数`);

        document.getElementById('nodeCount').textContent =
            `${totalFuncs} 个函数`;

    } catch (error) {
        progressFill.style.width = '0%';
        progressText.textContent = '❌ ' + error.message;
        setStatus('错误: ' + error.message);
        console.error('扫描失败:', error);
    } finally {
        scanBtn.disabled = false;
        setTimeout(() => {
            progressRow.style.display = 'none';
        }, 3000);
    }
}

// ===== 填充左侧列表 =====
function populateSidebar(data) {
    const container = document.getElementById('sidebarContent');
    container.innerHTML = '';

    let totalFuncs = 0;

    data.forEach(fileGroup => {
        totalFuncs += fileGroup.functions.length;
        const groupDiv = document.createElement('div');
        groupDiv.className = 'file-group';

        // 文件头（可折叠）
        const header = document.createElement('div');
        header.className = 'file-group-header';
        const shortPath = fileGroup.file_path.replace(/\\/g, '/').split('/').slice(-3).join('/');
        header.innerHTML = `<span class="toggle-icon">▼</span>
                            ${escapeHtml(shortPath)}
                            <span style="color:#bbb;font-weight:400;margin-left:auto;font-size:11px;">
                                ${fileGroup.functions.length}
                            </span>`;
        header.onclick = () => header.classList.toggle('collapsed');
        groupDiv.appendChild(header);

        // 函数列表
        const children = document.createElement('div');
        children.className = 'file-group-children';

        fileGroup.functions.forEach(func => {
            const entry = document.createElement('div');
            entry.className = 'func-entry';
            entry.dataset.funcId = func.id;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'func-name';
            nameSpan.textContent = func.short_name;
            entry.appendChild(nameSpan);

            if (func.params && func.params.length > 0) {
                const paramsSpan = document.createElement('span');
                paramsSpan.className = 'func-params';
                paramsSpan.innerHTML = '(' + func.params.map(p =>
                    `<span class="param" onclick="event.stopPropagation();handleParamClick('${escapeJsString(func.id)}', '${escapeJsString(p)}')">${escapeHtml(p)}</span>`
                ).join(', ') + ')';
                entry.appendChild(paramsSpan);
            }

            entry.onclick = () => onSidebarFunctionClick(func.id);
            children.appendChild(entry);
        });

        groupDiv.appendChild(children);
        container.appendChild(groupDiv);
    });

    document.getElementById('sidebarCount').textContent = `${totalFuncs} 个函数`;
}

// ===== 点击sidebar中的函数 =====
async function onSidebarFunctionClick(funcId) {
    if (!currentGraphId) return;

    // 检查函数是否有效（外部函数无法展开子图）
    const exists = sidebarData.some(g => g.functions.some(f => f.id === funcId));
    if (!exists) {
        setStatus('外部函数，无法展开子图');
        return;
    }

    // 更新sidebar选中状态
    document.querySelectorAll('.func-entry.active').forEach(el => el.classList.remove('active'));
    document.querySelectorAll(`.func-entry[data-func-id="${CSS.escape(funcId)}"]`)
        .forEach(el => el.classList.add('active'));

    currentFuncId = funcId;

    // 清除参数流高亮
    clearParamFlow();

    // 获取子图
    try {
        setStatus(`加载子图: ${funcId.split('::').pop()}...`);

        const resp = await fetch(
            `/api/graph/${currentGraphId}/subgraph?func_id=${encodeURIComponent(funcId)}&depth=3`
        );
        if (!resp.ok) throw new Error('获取子图失败');
        const data = await resp.json();

        renderSubgraph(data);

        // 显示右侧详情
        showFunctionDetail(funcId);

        setStatus(`子图: ${data.nodes.length} 个节点, ${data.edges.length} 条边 (中心: ${data.center.split('::').pop()})${data.truncated ? ' ⚠️ 节点过多已截断' : ''}`);
    } catch (error) {
        console.error('获取子图失败:', error);
        setStatus('错误: ' + error.message);
    }
}

// ===== 渲染子图（层级布局 + 外部节点） =====
function renderSubgraph(data) {
    const container = document.getElementById('graphArea');

    // 销毁旧网络
    if (network) {
        network.destroy();
        network = null;
    }

    // 创建节点数据集
    nodesDataset = new vis.DataSet(data.nodes.map(n => ({
        id: n.id,
        label: n.label || n.id.split('::').pop(),
        title: n.is_external ? `[外部函数] ${n.label}` : (n.title || n.id),
        color: getLanguageColor(n.is_external ? 'external' : (n.language || n.group || '')),
        size: n.is_external ? 15 : (n.depth === 0 ? 30 : (n.depth === 1 ? 24 : 18)),
        shape: n.is_external ? 'box' : 'dot',
        file: n.file || '',
        language: n.language || '',
        params: n.params || [],
        group: n.group || '',
        depth: n.depth || 0,
        level: n.level !== undefined ? n.level : undefined,
        borderWidth: n.is_external ? 1 : (n.depth === 0 ? 4 : 2),
        is_external: n.is_external || false,
    })));

    // 创建边数据集
    edgesDataset = new vis.DataSet(data.edges.map(e => ({
        from: e.from,
        to: e.to,
        label: '',  // 默认不显示参数标签
        title: e.title || '',
        dashes: e.dashes || false,
        color: e.dashes
            ? { color: 'rgba(200,200,200,0.5)', inherit: false }
            : { color: 'rgba(100,100,100,0.6)', inherit: false },
        width: e.dashes ? 1 : 1.5,
        arrows: 'to',
        smooth: { type: 'continuous' },
        _args: e.args || [],
    })));

    const options = {
        layout: {
            hierarchical: {
                enabled: true,
                direction: 'LR',
                sortMethod: 'directed',
                levelSeparation: 200,
                nodeSpacing: 150,
                treeSpacing: 200,
                blockShifting: true,
                edgeMinimization: true,
                parentCentralization: true,
            },
        },
        physics: {
            enabled: false,
        },
        edges: {
            smooth: { type: 'continuous', roundness: 0.5 },
            font: { size: 10, strokeWidth: 2, align: 'middle' },
        },
        nodes: {
            font: { size: 14, face: 'Arial' },
            borderWidth: 2,
            shadow: { enabled: true, size: 4 },
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: true,
            keyboard: true,
        },
    };

    // 显示graph区域
    document.getElementById('graphPlaceholder').style.display = 'none';
    document.getElementById('graphArea').style.display = 'block';

    network = new vis.Network(container, { nodes: nodesDataset, edges: edgesDataset }, options);

    // 布局完成后聚焦中心节点
    network.once('afterDrawing', function() {
        if (data.center) {
            network.focus(data.center, { scale: 1.2, animation: false });
        }
    });

    // 事件绑定
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const nodeData = nodesDataset.get(nodeId);
            if (nodeData && nodeData.is_external) {
                showExternalFunctionDetail(nodeId, nodeData);
            } else {
                showFunctionDetail(nodeId);
            }
            highlightNode(nodeId);
        } else {
            clearHighlight();
        }
    });

    network.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const nodeData = nodesDataset.get(nodeId);
            if (nodeData && !nodeData.is_external) {
                onSidebarFunctionClick(nodeId);
            }
        }
    });

    network.on('oncontext', function(params) {
        params.event.preventDefault();
        return false;
    });
}

// ===== 显示函数详情 =====
async function showFunctionDetail(funcId) {
    if (!currentGraphId || !funcId) return;

    const panel = document.getElementById('detailPanel');
    const content = document.getElementById('detailContent');

    panel.classList.remove('hidden');
    content.innerHTML = '<p style="text-align:center;color:#999;">加载中...</p>';

    try {
        const resp = await fetch(`/api/function/${currentGraphId}?func_id=${encodeURIComponent(funcId)}`);
        if (!resp.ok) {
            content.innerHTML = `<p style="color:#e74c3c;">加载失败: ${resp.status}</p>`;
            return;
        }

        const data = await resp.json();

        let html = '<div class="detail-card">';
        html += `<h4>📌 ${escapeHtml(data.short_name || data.name)}</h4>`;

        html += '<div class="detail-item"><span class="label">签名:</span>';
        html += `<span class="value">${escapeHtml(data.signature || '')}</span></div>`;

        html += '<div class="detail-item"><span class="label">文件:</span>';
        html += `<span class="value">${escapeHtml(data.file_path || '')}</span></div>`;

        html += '<div class="detail-item"><span class="label">语言:</span>';
        html += `<span class="value">${escapeHtml(data.language || '')}</span></div>`;

        html += '<div class="detail-item"><span class="label">行号:</span>';
        html += `<span class="value">${data.line_start || '?'} - ${data.line_end || '?'}</span></div>`;

        if (data.class_name) {
            html += '<div class="detail-item"><span class="label">所属类:</span>';
            html += `<span class="value">${escapeHtml(data.class_name)}</span></div>`;
        }

        if (data.return_type) {
            html += '<div class="detail-item"><span class="label">返回类型:</span>';
            html += `<span class="value">${escapeHtml(data.return_type)}</span></div>`;
        }

        html += '</div>';

        // 参数列表（每个参数可点击追踪流向）
        if (data.params && data.params.length > 0) {
            html += '<div class="detail-card">';
            html += '<h4>📝 参数 <span style="font-size:11px;font-weight:400;color:#999;">（点击追踪流向）</span></h4>';
            html += '<div class="detail-item">';
            html += '<span class="value">';
            html += data.params.map(p =>
                `<span class="param-link" onclick="traceParamFlow('${escapeJsString(data.id)}', '${escapeJsString(p)}')">${escapeHtml(p)}</span>`
            ).join(', ');
            html += '</span></div></div>';
        }

        // 调用者
        html += '<div class="detail-card">';
        html += `<h4>⬆️ 调用者 (${(data.callers || []).length})</h4>`;
        if (data.callers && data.callers.length > 0) {
            html += '<ul class="call-list">';
            data.callers.forEach(caller => {
                const isResolved = caller.is_resolved !== false;
                const callerName = caller.id.split('::').pop() || caller.callee_name || '?';
                const argsText = (caller.args && caller.args.length > 0)
                    ? `传参: ${caller.args.join(', ')}` : '';
                html += `<li class="call-item ${isResolved ? '' : 'unresolved'}"
                            onclick="${isResolved ? `onSidebarFunctionClick('${escapeJsString(caller.id)}')` : ''}"
                            style="${isResolved ? '' : 'cursor:default;'}">
                            <span class="line-num">行 ${caller.line || '?'}</span>
                            <span class="func-name">${escapeHtml(callerName)}</span>
                            ${argsText ? `<span class="args">${escapeHtml(argsText)}</span>` : ''}
                            ${!isResolved ? '<span style="color:#999;font-size:11px;"> [外部函数]</span>' : ''}
                        </li>`;
            });
            html += '</ul>';
        } else {
            html += '<p style="color:#999;font-size:13px;">没有被调用（可能是入口函数）</p>';
        }
        html += '</div>';

        // 被调用者
        html += '<div class="detail-card">';
        html += `<h4>⬇️ 调用的函数 (${(data.callees || []).length})</h4>`;
        if (data.callees && data.callees.length > 0) {
            html += '<ul class="call-list">';
            data.callees.forEach(callee => {
                const isResolved = callee.is_resolved !== false;
                const calleeName = callee.id.split('::').pop() || callee.callee_name || '?';
                const argsText = (callee.args && callee.args.length > 0)
                    ? `实参: ${callee.args.join(', ')}` : '（无参数）';
                html += `<li class="call-item ${isResolved ? '' : 'unresolved'}"
                            onclick="${isResolved ? `onSidebarFunctionClick('${escapeJsString(callee.id)}')` : ''}"
                            style="${isResolved ? '' : 'cursor:default;'}">
                            <span class="line-num">行 ${callee.line || '?'}</span>
                            <span class="func-name">${escapeHtml(calleeName)}</span>
                            ${argsText ? `<span class="args">${escapeHtml(argsText)}</span>` : ''}
                            ${!isResolved ? '<span style="color:#999;font-size:11px;"> [外部函数]</span>' : ''}
                        </li>`;
            });
            html += '</ul>';
        } else {
            html += '<p style="color:#999;font-size:13px;">没有调用其他函数（叶子函数）</p>';
        }
        html += '</div>';

        content.innerHTML = html;

    } catch (error) {
        content.innerHTML = `<p style="color:#e74c3c;">加载失败: ${escapeHtml(error.message)}</p>`;
        console.error('获取函数详情失败:', error);
    }
}

// ===== 显示外部函数信息（无需API调用） =====
function showExternalFunctionDetail(nodeId, nodeData) {
    const panel = document.getElementById('detailPanel');
    const content = document.getElementById('detailContent');

    panel.classList.remove('hidden');

    let html = '<div class="detail-card">';
    html += '<h4>🔌 外部函数</h4>';
    html += '<div class="detail-item"><span class="label">名称:</span>';
    html += `<span class="value">${escapeHtml(nodeData.label)}</span></div>`;
    html += '<div class="detail-item"><span class="label">来源:</span>';
    html += '<span class="value">未在当前扫描目录中找到该函数的定义</span></div>';

    if (nodeData.title && nodeData.title.startsWith('[外部函数]')) {
        html += '<div class="detail-item"><span class="label">完整名称:</span>';
        html += `<span class="value" style="word-break:break-all;">${escapeHtml(nodeData.title.replace('[外部函数] ', ''))}</span></div>`;
    }

    html += '<p style="color:#999;font-size:13px;margin-top:16px;line-height:1.6;">';
    html += '外部函数通常是标准库、第三方库或未扫描路径中的函数。<br>';
    html += '无法查看其内部调用关系，但可以查看哪些函数调用了它。</p>';
    html += '</div>';

    content.innerHTML = html;
}

// ===== 处理参数点击（先确保选中函数，再追踪流向） =====
async function handleParamClick(funcId, paramName) {
    if (!currentGraphId || !funcId) return;

    // 如果当前没有选中函数，或者选中的不是该函数，先切换
    if (currentFuncId !== funcId) {
        // 检查该函数在 sidebar 中是否存在
        const exists = sidebarData.some(g => g.functions.some(f => f.id === funcId));
        if (!exists) {
            setStatus('外部函数，无法展开子图');
            return;
        }

        // 清除当前参数流，然后切换到该函数（等待子图加载完成）
        clearParamFlow();

        // 更新 sidebar 选中状态
        document.querySelectorAll('.func-entry.active').forEach(el => el.classList.remove('active'));
        document.querySelectorAll(`.func-entry[data-func-id="${CSS.escape(funcId)}"]`)
            .forEach(el => el.classList.add('active'));

        currentFuncId = funcId;

        try {
            setStatus(`加载子图: ${funcId.split('::').pop()}...`);

            const resp = await fetch(
                `/api/graph/${currentGraphId}/subgraph?func_id=${encodeURIComponent(funcId)}&depth=3`
            );
            if (!resp.ok) throw new Error('获取子图失败');
            const data = await resp.json();

            renderSubgraph(data);
            showFunctionDetail(funcId);

            setStatus(`子图: ${data.nodes.length} 个节点, ${data.edges.length} 条边${data.truncated ? ' ⚠️ 节点过多已截断' : ''}`);
        } catch (error) {
            console.error('获取子图失败:', error);
            setStatus('错误: ' + error.message);
            return;
        }
    }

    // 现在执行参数流向追踪
    traceParamFlow(funcId, paramName);
}

// ===== 追踪参数流向 =====
async function traceParamFlow(funcId, paramName) {
    if (!currentGraphId || !funcId || !edgesDataset) return;

    try {
        setStatus(`追踪参数: ${paramName}...`);

        const resp = await fetch(
            `/api/graph/${currentGraphId}/param-flow?func_id=${encodeURIComponent(funcId)}&param=${encodeURIComponent(paramName)}`
        );
        if (!resp.ok) throw new Error('获取参数流失败');
        const data = await resp.json();

        // 收集受影响的边ID
        const involvedEdgeIds = new Set();

        // 传入: 红色
        data.incoming.forEach(flow => {
            edgesDataset.forEach(edge => {
                if (edge.from === flow.from && edge.to === flow.to) {
                    edgesDataset.update({
                        id: edge.id,
                        color: { color: '#E74C3C', inherit: false },
                        width: 3,
                        label: flow.caller_arg || '',
                        font: { color: '#E74C3C', size: 11, strokeWidth: 2 },
                    });
                    involvedEdgeIds.add(edge.id);
                }
            });
        });

        // 传出: 绿色
        data.outgoing.forEach(flow => {
            edgesDataset.forEach(edge => {
                if (edge.from === flow.from && edge.to === flow.to) {
                    edgesDataset.update({
                        id: edge.id,
                        color: { color: '#2ECC71', inherit: false },
                        width: 3,
                        label: flow.forwarded_as || '',
                        font: { color: '#2ECC71', size: 11, strokeWidth: 2 },
                    });
                    involvedEdgeIds.add(edge.id);
                }
            });
        });

        // 其他边变灰
        edgesDataset.forEach(edge => {
            if (!involvedEdgeIds.has(edge.id)) {
                edgesDataset.update({
                    id: edge.id,
                    color: { color: 'rgba(200,200,200,0.15)', inherit: false },
                    width: 1,
                });
            }
        });

        // 显示参数流信息条
        const flowInfo = document.getElementById('paramFlowInfo');
        const paramDisplay = escapeHtml(paramName);
        const funcDisplay = escapeHtml(funcId.split('::').pop());
        flowInfo.innerHTML = `<span>🔍 追踪: <strong>${paramDisplay}</strong> 在 <strong>${funcDisplay}</strong>
            | 传入: ${data.incoming.length} | 传出: ${data.outgoing.length}</span>
            <button id="clearFlowBtn" onclick="clearParamFlow()">清除</button>`;
        flowInfo.classList.add('visible');

        setStatus(`参数流: ${paramName} → ${data.incoming.length}个传入, ${data.outgoing.length}个传出`);

    } catch (error) {
        console.error('参数流追踪失败:', error);
        setStatus('错误: ' + error.message);
    }
}

// ===== 清除参数流高亮 =====
function clearParamFlow() {
    if (!edgesDataset) return;

    edgesDataset.forEach(edge => {
        const isDashed = edge.dashes || false;
        edgesDataset.update({
            id: edge.id,
            label: '',  // 恢复默认不显示参数标签
            color: isDashed
                ? { color: 'rgba(200,200,200,0.5)', inherit: false }
                : { color: 'rgba(100,100,100,0.6)', inherit: false },
            width: isDashed ? 1 : 1.5,
        });
    });

    document.getElementById('paramFlowInfo').classList.remove('visible');
}

// ===== 节点高亮 =====
function highlightNode(nodeId) {
    if (!network || !nodesDataset) return;

    clearHighlight();

    const connectedNodes = network.getConnectedNodes(nodeId);
    const connectedEdges = network.getConnectedEdges(nodeId);

    nodesDataset.forEach(node => {
        if (node.id === nodeId) {
            nodesDataset.update({ id: nodeId, color: { background: '#FFD700', border: '#FF8C00' },
                                   borderWidth: 4 });
        } else if (connectedNodes.includes(node.id)) {
            nodesDataset.update({ id: node.id, opacity: 1.0 });
        } else {
            nodesDataset.update({ id: node.id, opacity: 0.3 });
        }
    });

    edgesDataset.forEach(edge => {
        if (connectedEdges.includes(edge.id)) {
            edgesDataset.update({ id: edge.id, color: { color: '#FF8C00', inherit: false },
                                   width: 3 });
        } else {
            edgesDataset.update({ id: edge.id, color: { color: 'rgba(200,200,200,0.15)', inherit: false } });
        }
    });
}

function clearHighlight() {
    if (!nodesDataset || !edgesDataset) return;

    nodesDataset.forEach(node => {
        const isExt = node.is_external || false;
        nodesDataset.update({
            id: node.id,
            color: getLanguageColor(isExt ? 'external' : (node.language || node.group || '')),
            borderWidth: node.borderWidth || (node.depth === 0 ? 4 : 2),
            opacity: 1.0,
        });
    });

    edgesDataset.forEach(edge => {
        const isDashed = edge.dashes || false;
        edgesDataset.update({
            id: edge.id,
            color: isDashed ? { color: 'rgba(200,200,200,0.5)', inherit: false }
                            : { color: 'rgba(100,100,100,0.6)', inherit: false },
            width: isDashed ? 1 : 1.5,
        });
    });
}

// ===== 搜索（改为搜索 sidebarData） =====
function toggleSearch() {
    const overlay = document.getElementById('searchOverlay');
    overlay.classList.toggle('hidden');
    if (!overlay.classList.contains('hidden')) {
        document.getElementById('searchInput').focus();
    }
}

function hideSearch() {
    document.getElementById('searchOverlay').classList.add('hidden');
    document.getElementById('searchResults').innerHTML = '';
}

function searchFunction(query) {
    const results = document.getElementById('searchResults');
    if (!query || query.length < 1) {
        results.innerHTML = '';
        return;
    }

    query = query.toLowerCase();
    const allFuncs = sidebarData.flatMap(g => g.functions);
    const matches = allFuncs.filter(f => {
        return f.short_name.toLowerCase().includes(query)
            || f.id.toLowerCase().includes(query);
    }).slice(0, 20);

    if (matches.length === 0) {
        results.innerHTML = '<div style="padding:12px 16px;color:#999;">未找到匹配的函数</div>';
        return;
    }

    results.innerHTML = matches.map(f => {
        const highlightedLabel = f.short_name.replace(
            new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'),
            match => `<span class="highlight">${match}</span>`
        );
        return `<div class="search-result-item"
                     onclick="onSidebarFunctionClick('${escapeJsString(f.id)}'); hideSearch();">
                    ${highlightedLabel}
                    <span class="file-path">${escapeHtml(f.file_path)}</span>
                </div>`;
    }).join('');
}

// ===== Sidebar 筛选 =====
function filterSidebar(query) {
    const entries = document.querySelectorAll('.func-entry');
    const fileGroups = document.querySelectorAll('.file-group');

    query = query.toLowerCase().trim();

    if (!query) {
        entries.forEach(el => el.style.display = 'flex');
        fileGroups.forEach(el => el.style.display = '');
        return;
    }

    fileGroups.forEach(group => {
        let visibleCount = 0;
        group.querySelectorAll('.func-entry').forEach(entry => {
            const name = entry.querySelector('.func-name').textContent.toLowerCase();
            const match = name.includes(query);
            entry.style.display = match ? 'flex' : 'none';
            if (match) visibleCount++;
        });
        group.style.display = visibleCount === 0 ? 'none' : '';
    });
}

// ===== 辅助函数 =====
function closeDetail() {
    document.getElementById('detailPanel').classList.add('hidden');
    clearHighlight();
}

function resetView() {
    if (network) {
        network.fit({ animation: true });
        clearHighlight();
    }
}

function setStatus(text) {
    document.getElementById('statusText').textContent = text;
}

function getLanguageColor(language) {
    const colors = {
        'python': { background: '#3572A5', border: '#2A5A8A' },
        'cpp': { background: '#F34B7D', border: '#D43D6A' },
        'c': { background: '#555555', border: '#3D3D3D' },
        'matlab': { background: '#E16737', border: '#B8542E' },
        'external': { background: '#BDC3C7', border: '#95A5A6' },
    };
    return colors[language] || { background: '#97C2FC', border: '#7DAADC' };
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * 转义字符串，使其可安全嵌入到 onclick 等 HTML 属性中的 JavaScript 字符串字面量。
 *
 * 解决了 Windows 路径中的反斜杠被 JS 解释为转义序列的问题。
 * 例如: 路径 d:\codeing\test 中的 \t 会被 JS 当作 TAB 字符，
 * \co 会被当作控制字符，导致字符串损坏。
 *
 * 实现: 先转义 JS 字符串特殊字符 (\, ', \n, \r, \t)，
 * 再转义 HTML 特殊字符 (&, ", <, >)，确保嵌入 HTML onclick="" 属性安全。
 */
function escapeJsString(str) {
    if (!str) return '';
    return String(str)
        .replace(/\\/g, '\\\\')    // 反斜杠 -> \\ (防止JS转义序列)
        .replace(/'/g, "\\'")      // 单引号 -> \' (防止破坏JS字符串边界)
        .replace(/\n/g, '\\n')     // 换行 -> \n
        .replace(/\r/g, '\\r')     // 回车 -> \r
        .replace(/\t/g, '\\t')     // Tab -> \t
        .replace(/"/g, '&quot;')   // 双引号 -> HTML实体 (防止破坏HTML属性边界)
        .replace(/&/g, '&amp;')    // & -> HTML实体
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
