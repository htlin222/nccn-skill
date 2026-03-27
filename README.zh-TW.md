# create-skill-to-treat-cancer

將 NCCN 臨床實務指引 PDF 轉換為結構化 AI 技能套件的元技能（meta-skill），遵循 [Vercel Skills 協定](https://github.com/vercel-labs/skills)。

[English](README.md) | **繁體中文**

## 免責聲明

> **本專案僅供研究與測試用途。**
>
> 產生的技能套件**並非用於取代 NCCN 臨床實務指引正式版本**。其內容係透過自動化擷取與 AI 輔助轉換而來，過程中可能產生錯誤、遺漏或失真。
>
> - **僅限具有執照的醫療專業人員使用。** 本工具旨在協助已熟悉 NCCN 指引的臨床醫師，不應由病患或非醫療人員用於臨床決策。
> - **請謹慎使用。** 在做出臨床決策前，務必以原版 NCCN 指引 PDF 及現行院內規範進行交叉驗證。
> - **非醫療器材。** 本軟體未經臨床驗證，不構成醫療建議。
> - **NCCN 內容受著作權保護。** 使用者須自行確保符合 NCCN 使用條款。本儲存庫不包含原始 PDF 檔案。

## 概述

NCCN 指引 PDF 通常超過 300 頁，涵蓋癌症的診斷、分期、各線治療、支持性照護及實證討論。本專案提供一條自動化流水線，將其轉換為模組化、可導覽的 AI 技能套件，具備漸進式揭露（progressive disclosure）機制：

```
PDF（357 頁）→ 目錄擷取 → 語意分段 → 平行 Haiku 轉換 → 合併 → 驗證 → 技能套件
```

**已生成 5 個技能套件**（處理 1,382 頁 PDF）：

| 癌種 | 版本 | 檔案數 | 行數 | 引用數 |
|---|---|---|---|---|
| B 細胞淋巴瘤 | v3.2025 | 34 | 8,592 | 3,479 |
| 乳癌 | v2.2026 | 24 | 4,008 | 1,866 |
| 非小細胞肺癌 | v3.2026 | 36 | 5,691 | 2,796 |
| 急性骨髓性白血病 | v3.2026 | 34 | 5,566 | 1,668 |
| 大腸癌 | v2.2026 | 33 | 8,765 | 2,065 |
| **合計** | | **161** | **32,622** | **11,874** |

## 架構

```
create-skill-to-treat-cancer/     # 元技能（不限癌種）
├── SKILL.md                      # 六步驟協作流程
├── scripts/                      # 流水線腳本（Python + PyMuPDF）
│   ├── extract_toc.py            # PDF 目錄 → toc.json
│   ├── chunk_pdf.py              # 語意分段，自動拆分大區塊（--max-chars）
│   ├── merge_parts.py            # 合併多段轉換結果為單一參考檔
│   ├── assemble_skill.py         # 生成分類式 SKILL.md + 組織 references/
│   ├── quality_gate.py           # 識別低品質輸出，自動重試
│   ├── validate_links.py         # 防孤兒連結：連結完整性檢查
│   ├── validate_citations.py     # 防幻覺：[p.XX] 引用覆蓋率檢查
│   └── check_format.py           # Vercel Skills 協定合規性檢查
├── references/                   # 轉換提示詞、分派協定、文件
└── assets/                       # 範本與範例分類檔

nccn-cancer-skill/                # 生成的技能套件（已提交）
├── b-cell-lymphomas/             # 34 檔 — FL、MCL、DLBCL、Burkitt、MZL、HGBL...
├── breast-cancer/                # 24 檔 — DCIS、侵襲性、TNBC、HER2+、HR+...
├── nscl/                         # 36 檔 — EGFR、ALK、ROS1、PD-L1、分期...
├── aml/                          # 34 檔 — APL、AML 誘導/鞏固、BPDCN...
└── colon/                        # 33 檔 — 分期、輔助、轉移、MSI、KRAS...

tmp/                              # 中間產物（已 gitignore）
└── <cancer-name>/                # toc.json、chunks/、converted/、merged/
```

## 快速開始

```bash
# 前置需求
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf pyyaml

# 步驟 1-2：擷取目錄與分段
CANCER=breast-cancer  # 修改為你的癌種
mkdir -p tmp/${CANCER}

python create-skill-to-treat-cancer/scripts/extract_toc.py path/to/nccn.pdf --output tmp/${CANCER}/toc.json
python create-skill-to-treat-cancer/scripts/chunk_pdf.py path/to/nccn.pdf \
  --toc tmp/${CANCER}/toc.json --output-dir tmp/${CANCER}/chunks --max-chars 50000

# 步驟 3：透過 Haiku 平行轉換（詳見 references/haiku-dispatch-protocol.md）
# 步驟 4：合併與組裝
python create-skill-to-treat-cancer/scripts/merge_parts.py \
  --input-dir tmp/${CANCER}/converted --output-dir tmp/${CANCER}/merged
python create-skill-to-treat-cancer/scripts/assemble_skill.py \
  --chunks-dir tmp/${CANCER}/merged --toc tmp/${CANCER}/toc.json \
  --output-dir nccn-cancer-skill/${CANCER} \
  --template create-skill-to-treat-cancer/assets/skill-md-template.yaml \
  --guideline-name "<指引名稱>" --version "<版本>"

# 步驟 5：驗證
python create-skill-to-treat-cancer/scripts/validate_links.py nccn-cancer-skill/${CANCER}/
python create-skill-to-treat-cancer/scripts/validate_citations.py nccn-cancer-skill/${CANCER}/
python create-skill-to-treat-cancer/scripts/check_format.py nccn-cancer-skill/${CANCER}/
```

## 防幻覺設計

生成的技能套件中，每一項事實性陳述都必須附帶 `[p.XX]` 頁碼引用，可追溯至原始 PDF。流水線透過以下機制強制執行：

1. **`[PAGE XX]` 標記** — 文字擷取時嵌入頁碼標記
2. **Haiku 提示詞指令** — 要求每一項藥物、劑量、證據分級、建議都必須附帶引用
3. **`validate_citations.py`** — 標記未引用區段與超出範圍的頁碼
4. **`quality_gate.py`** — 識別引用密度低於閾值的檔案，自動重試
5. **區塊拆分**（`--max-chars 50000`）— 防止 Haiku 因輸入過大而截斷內容

## 引用

若您在研究中使用本軟體，請以下列格式引用：

### AMA（美國醫學會）格式

Lin HT. create-skill-to-treat-cancer: NCCN Guideline PDF to AI Skill Package Converter. Published 2026. Accessed March 26, 2026. https://github.com/htlin222/nccn-skill

### BibTeX

```bibtex
@software{lin2026nccnskill,
  author       = {Lin, Hsieh-Ting},
  title        = {create-skill-to-treat-cancer: {NCCN} Guideline {PDF} to {AI} Skill Package Converter},
  year         = {2026},
  url          = {https://github.com/htlin222/nccn-skill},
  version      = {1.0.0},
  license      = {Apache-2.0}
}
```

### CITATION.cff

儲存庫根目錄包含機器可讀的 `CITATION.cff` 檔案。

## 授權

Apache-2.0。詳見 [LICENSE](LICENSE)。

NCCN Clinical Practice Guidelines in Oncology 之著作權屬於 National Comprehensive Cancer Network。本專案不包含亦不散布 NCCN 內容。使用者須自行取得 NCCN 指引之合法授權。
