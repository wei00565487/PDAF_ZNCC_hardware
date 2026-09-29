---
id: index
title: Bayer 混色シミュレーション（bxsim）— 索引
type: index
tags: [image-sensor, crosstalk, bayer, rgb-ir, bpm, fdtd, meep, optics]
updated: 2026-09-08
related: [00-overview, 20-physics-model, 21-validation, 40-design-insights, 70-assumptions]
source_of_truth: C:\Users\tachi\Documents\bayer-crosstalk-sim（bxsim 0.1.0）
---

# Bayer 混色シミュレーション（bxsim）— 索引

## 要約

有償の光学 / デバイスシミュレータ（Lumerical FDTD, Zemax, Sentaurus, Silvaco 等）を使わずに、
Bayer 配列 CMOS イメージセンサの**混色（クロストーク）**を定量評価する Python パッケージと、
そこから得られた知見。依存は numpy / scipy / matplotlib のみ。

混色を、設計レバーが異なる 3 成分に分離して出す。

| 成分 | 物理 | 手法 |
|---|---|---|
| 分光クロストーク | CFA 透過帯の重なり、NIR 漏れ | 分光透過率の重み付け |
| 光学クロストーク | 回折、斜入射での隣画素漏れ込み | 角スペクトル法 BPM |
| 電気クロストーク | Si 深部で生成したキャリアの横方向拡散 | 拡散方程式の**随伴解** |

随伴法を使うのが本ツールの要で、**線形ソルブ 1 回で全波長・全入射角・全 CFA 色**のカーネルが
出る。31 波長 × 4 構成のスイープが 1 分弱で回る（→ [[20-physics-model]]）。

検証は独立に 2 系統で通っている。全開口照射時の Si 吸収が Beer-Lambert 解析解と 1e-8 で一致し、
キャリア収集確率の総和が 1.000000 になる（→ [[21-validation]]）。

## ページ一覧

| ページ | 内容 |
|---|---|
| [00-overview](00-overview.md) | 何ができるか、ファイル構成、成果物一覧 |
| [10-setup](10-setup.md) | 実行方法、スクリプト一覧、所要時間 |
| [20-physics-model](20-physics-model.md) | BPM・随伴拡散・F 値光束の定式化 |
| [21-validation](21-validation.md) | 検証記録。**通った検証と、通っていない検証** |
| [30-results](30-results.md) | DTI 深さ・CRA・F 値・構造オプションの結果 |
| [31-rgbir](31-rgbir.md) | RGB-IR 4x4 の 6 個の G 画素。**軸上でも縮退が解ける** |
| [32-image-quality](32-image-quality.md) | Gr/Gb アンバランスと画質影響の定量 |
| [40-design-insights](40-design-insights.md) | 設計知見と、**途中で訂正した 4 つの誤り** |
| [50-fdtd-meep](50-fdtd-meep.md) | Meep FDTD による厳密検証。**未完了** |
| [60-roadmap](60-roadmap.md) | 未検証事項・次にやること |
| [70-assumptions](70-assumptions.md) | **仮定値の一覧と感度**。数値を引用する前に必読 |
| [80-dual-pd-zncc-hardware](80-dual-pd-zncc-hardware.md) | Dual-PD位相差検出のZNCC参照モデルとラインメモリ／演算器設計 |
| [90-glossary](90-glossary.md) | 用語集 |

## この wiki の使い方

- front matter + `## 要約` + 相互リンクの形式は [[infinite-isp-project]] / [[action-cam-sensor-ledger]] と共通。RAG 投入を想定。
- **数値を引用する前に [[70-assumptions]] を読むこと。** CFA 厚・透過カーブ・K 画素カーブは
  実測ではなく仮定値であり、混色の絶対値はこれらに直接依存する。
- 実測値には日付を明記する。2026-09-08 の値は bxsim 0.1.0 / Meep 1.29.0（WSL Ubuntu 26.04）。
- 未確定の事項は [[60-roadmap]] に集約してある。断定していない箇所を断定に変えないこと。
