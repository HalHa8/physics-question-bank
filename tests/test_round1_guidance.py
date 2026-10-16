"""Round-one guidance and executable PDF failure recovery regressions."""

from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_safe_sharing_guidance_distinguishes_restore_from_sharing():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    guide = html.split('id="qaSafeSharing"', 1)[1].split("</section>", 1)[0]
    assert "不要把整个程序文件夹打包" in guide
    assert "完整备份用于恢复自己的题库" in guide
    assert "系统备份会排除 API 密钥" in guide
    assert "尚未提供" in guide
    assert "作废、重建可能泄露的密钥" in guide
    assert "onclick=" not in guide  # Documentation must not trigger model calls or downloads.
    assert "qaSafeSharingTitle" in guide


def test_pdf_diagnostic_actions_copy_fallback_and_download_exact_source():
    source = (ROOT / "static/js/paper.js").read_text(encoding="utf-8")
    start = source.index("function bindPdfDiagnosticActions(")
    shipped = source[start:source.index("function setPandocModalVisible(", start)]
    harness = r"""
const assert = require('node:assert/strict');
const elements = Object.fromEntries(['copyPdfDiagnostic','pdfDiagnosticStatus',
 'pdfDiagnosticCopyFallback','downloadFailedTex'].map(id=>[id,{hidden:true,focus(){},select(){}}]));
let copied='', downloaded='', removed=false, blob=null, revoked='';
const tab = {
 document: {
  getElementById:id=>elements[id], body:{appendChild(){}},
  createElement:()=>({click(){downloaded=this.download},remove(){removed=true}})
 },
 navigator:{clipboard:{async writeText(text){copied=text}}},
 URL:{createObjectURL(value){blob=value;return 'blob:local'},revokeObjectURL(value){revoked=value}},
 setTimeout(fn){fn()}
};
const report={summary:'编译失败',location:'卷面第2题',cause:'未识别命令',
 fixes:['核对原文'],original_excerpt:'单位 $m/s$',source_context:'25: \\bad{x}',technical_error:'Undefined control sequence'};
const exact='\\documentclass{article}\n% <script>not executed</script>\n单位原文';
(async()=>{
 bindPdfDiagnosticActions(tab,report,'fallback',exact);
 assert.equal(copied,''); assert.equal(blob,null);
 await elements.copyPdfDiagnostic.onclick();
 assert.ok(copied.includes('卷面第2题')); assert.ok(copied.includes('单位 $m/s$'));
 tab.navigator.clipboard.writeText=async()=>{throw Error('denied')};
 await elements.copyPdfDiagnostic.onclick();
 assert.equal(elements.pdfDiagnosticCopyFallback.hidden,false);
 assert.equal(elements.pdfDiagnosticCopyFallback.value,copied);
 elements.downloadFailedTex.onclick();
 assert.equal(await blob.text(),exact);
 assert.equal(downloaded,'physicsbank-failed-paper.tex'); assert.ok(removed);
 assert.equal(revoked,'blob:local');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    node = shutil.which("node")
    assert node, "Node is required for the executable regression"
    result = subprocess.run([node, "-e", shipped + harness], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_pdf_error_page_escapes_original_evidence_and_wires_all_export_paths():
    source = (ROOT / "static/js/paper.js").read_text(encoding="utf-8")
    assert "escapeHtml(report.original_excerpt)" in source
    assert "errData.tex_source" in source
    assert "errorData.tex_source" in source
    assert "bindPdfDiagnosticActions(tab, report" in source
