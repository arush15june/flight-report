# flight-report

Claude Code skill：搜尋 Google Flights 並產生結構化的機票比價報告。

## 功能

- 支援中英文自然語言查詢（「桃園到福岡直飛便宜機票」）
- 自動將中文城市名對應 IATA 機場代碼
- 三種搜尋模式：
  - **單程**（one-way）
  - **來回**（round-trip）：固定回程天數
  - **彈性來回**（flexible-roundtrip）：指定遊玩天數範圍，自動組合去回程最佳配對
- 去程抵達時間篩選（如「中午前到」）
- 廉航行李費用自動加計
- 請假天數計算（去程當天算請假，回程不算）
- 不完整航班資料自動過濾
- 產出繁體中文 Markdown 報告

## 檔案結構

```
flight-report/
├── SKILL.md                          # Skill 定義與流程指引
├── scripts/
│   ├── search_flights.py             # Google Flights 爬蟲（基於 fast-flights）
│   └── combine_flights.py            # 去回程組合配對腳本
├── references/
│   ├── airport-codes.md              # IATA 機場代碼對照表
│   └── report-template.md            # 報告模板（單程 + 來回）
└── evals/
    └── evals.json                    # 測試案例
```

## 使用方式

### 作為 Claude Code Skill

將此資料夾放在 `~/.claude/skills/flight-report/`，即可在 Claude Code 中觸發：

```
> 桃園到福岡 四月 直飛 玩4~5天 便宜來回機票
> 台北到大阪來回機票 六月 幫我比價
> Find cheap nonstop flights from TPE to NRT in April
```

### 獨立使用腳本

**搜尋航班：**

```bash
python scripts/search_flights.py \
  --origin TPE --destination KIX \
  --start-date 2026-04-01 --end-date 2026-04-30 \
  --trip-type one-way --nonstop \
  --sample-mode 1 --delay 2 \
  --currency TWD --output outbound.json
```

**組合去回程：**

```bash
python scripts/combine_flights.py \
  --outbound-json outbound.json \
  --return-json return.json \
  --min-days 4 --max-days 5 \
  --arrival-before 12:00 \
  --baggage-cost 2000 \
  --filter-complete \
  --output combos.json
```

## combine_flights.py 參數

| 參數 | 說明 |
|------|------|
| `--outbound-json` | 去程搜尋結果 JSON |
| `--return-json` | 回程搜尋結果 JSON |
| `--min-days` | 最少天數（含頭含尾） |
| `--max-days` | 最多天數（含頭含尾） |
| `--arrival-before` | 去程抵達時間上限（如 `12:00`） |
| `--baggage-cost` | 來回行李費用，預設 NT$2,000 |
| `--filter-complete` | 過濾掉缺少航班資訊的結果 |
| `--output` | 輸出檔案路徑 |

## 天數定義

- **含頭含尾**：出發日算第 1 天，回程日算最後一天
- 例：4/10 出發、4/13 回程 = **4天3夜**
- **請假天數**：去程當天一律算請假（除非 22:00 後起飛），回程當天不算

## 相依套件

```bash
pip install fast-flights
```

## License

MIT
