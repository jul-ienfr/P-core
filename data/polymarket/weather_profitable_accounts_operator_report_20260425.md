# Polymarket météo — rapport opérateur comptes rentables / marchés live

- Généré depuis: `data/polymarket/weather_profitable_accounts_classified_top100_live_refresh.csv` + `data/polymarket/weather_profitable_accounts_operator_summary.json`
- Recommandation globale: **paper_micro_only** — unique_profitable_weather_accounts_match_live_markets_but_extreme_price_blocks_normal_sizing
- Next actions: poll_direct_resolution_source, paper_micro_order_with_strict_limit_and_fill_tracking, do_not_use_normal_size_until_extreme_price_clears

## Brief Discord

```text
Météo Polymarket: 8 marché live avec comptes météo rentables. Reco globale: paper_micro_only.
- 2065018 — Hong Kong — 5 comptes (5 heavy), blocker=extreme_price, verdict=paper_micro, top=Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27
- 2065028 — Hong Kong — 5 comptes (5 heavy), blocker=none, verdict=watch_or_paper, top=Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27
- 2074350 — Dallas — 5 comptes (5 heavy), blocker=missing_tradeable_quote, verdict=watch_or_paper, top=Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79
- 2074460 — Hong Kong — 5 comptes (5 heavy), blocker=missing_tradeable_quote, verdict=watch_or_paper, top=Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27
- 2064908 — Dallas — 5 comptes (5 heavy), blocker=missing_tradeable_quote, verdict=watch_or_paper, top=Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79
```

## Top 25 comptes météo rentables globaux

| # | handle | weather PnL | weather volume | PnL/vol | classification | active | recent | profile |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 |  | $343,576.70 | $4,571,379.83 | 7.516% | profitable in weather but currently/recently generalist | 1 | 0 | https://polymarket.com/profile/0xf2f6af4f27ec2dcf4072095ab804016e14cd5817 |
| 2 |  | $277,050.19 | $9,972,308.56 | 2.778% | not enough public recent data to classify | 0 | 0 | https://polymarket.com/profile/0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1 |
| 3 |  | $121,335.48 | $8,835,337.51 | 1.373% | weather specialist / weather-heavy | 97 | 192 | https://polymarket.com/profile/0x594edb9112f526fa6a80b8f858a6379c8a2c1c11 |
| 4 |  | $118,426.47 | $739,900.98 | 16.006% | weather-heavy mixed | 0 | 31 | https://polymarket.com/profile/0x6af75d4e4aaf700450efbac3708cce1665810ff1 |
| 5 |  | $86,600.55 | $410,556.07 | 21.093% | profitable in weather but currently/recently generalist | 0 | 4 | https://polymarket.com/profile/0xe5c8026239919339b988fdb150a7ef4ea196d3e7 |
| 6 |  | $80,872.37 | $6,971,546.61 | 1.160% | weather-heavy mixed | 0 | 55 | https://polymarket.com/profile/0x0f37cb80dee49d55b5f6d9e595d52591d6371410 |
| 7 |  | $71,174.40 | $953,274.81 | 7.466% | weather specialist / weather-heavy | 15 | 151 | https://polymarket.com/profile/0x05e70727a2e2dcd079baa2ef1c0b88af06bb9641 |
| 8 |  | $64,617.33 | $2,362,463.72 | 2.735% | weather specialist / weather-heavy | 18 | 119 | https://polymarket.com/profile/0xd8f8c13644ea84d62e1ec88c5d1215e436eb0f11 |
| 9 |  | $63,460.27 | $1,418,954.65 | 4.472% | weather specialist / weather-heavy | 4 | 198 | https://polymarket.com/profile/0x331bf91c132af9d921e1908ca0979363fc47193f |
| 10 |  | $62,776.72 | $850,755.65 | 7.379% | weather-heavy mixed | 0 | 6 | https://polymarket.com/profile/0xecdbd79566a25693b9971c48d7de84bc05f7da79 |
| 11 |  | $57,190.13 | $1,833,451.17 | 3.119% | weather-heavy mixed | 4 | 1 | https://polymarket.com/profile/0xb74711992caf6d04fa55eecc46b8efc95311b050 |
| 12 |  | $57,179.74 | $1,788,233.33 | 3.198% | weather-heavy mixed | 2 | 71 | https://polymarket.com/profile/0xacc8e9dcabf9d65a5c78e3bec6941ed53a2b7d08 |
| 13 |  | $56,197.56 | $6,390,837.94 | 0.879% | weather specialist / weather-heavy | 2 | 200 | https://polymarket.com/profile/0x15ceffed7bf820cd2d90f90ea24ae9909f5cd5fa |
| 14 |  | $55,093.07 | $598,139.14 | 9.211% | weather-heavy mixed | 0 | 6 | https://polymarket.com/profile/0xf1bb700a67e3e8a45dc8160a92f4e0405f41bf09 |
| 15 |  | $51,421.33 | $161,054.39 | 31.928% | not enough public recent data to classify | 0 | 0 | https://polymarket.com/profile/0xc1b399b26020a4f689108e9640fd3dc8ffc8501c |
| 16 |  | $51,264.80 | $864,204.69 | 5.932% | profitable in weather but currently/recently generalist | 0 | 2 | https://polymarket.com/profile/0xdaad6f960d507dba148c1ff908db5a28743169cc |
| 17 |  | $50,781.10 | $741,105.84 | 6.852% | profitable in weather but currently/recently generalist | 0 | 1 | https://polymarket.com/profile/0x5a181dcf3eb53a09fb32b20a5a9312fb8d26f689 |
| 18 |  | $50,075.70 | $6,133,466.34 | 0.816% | weather specialist / weather-heavy | 63 | 180 | https://polymarket.com/profile/0xb40e89677d59665d5188541ad860450a6e2a7cc9 |
| 19 |  | $49,971.27 | $4,620,632.97 | 1.081% | weather specialist / weather-heavy | 96 | 198 | https://polymarket.com/profile/0x1f66796b45581868376365aef54b51eb84184c8d |
| 20 |  | $46,787.66 | $1,370,054.38 | 3.415% | weather specialist / weather-heavy | 6 | 127 | https://polymarket.com/profile/0x118689b24aead1d6e9507b8068d056b2ec4f051b |
| 21 |  | $45,558.18 | $3,188,650.65 | 1.429% | weather specialist / weather-heavy | 29 | 183 | https://polymarket.com/profile/0x57ee70867b4e387de9de34fd62bc685aa02a8112 |
| 22 |  | $44,961.86 | $2,101,745.48 | 2.139% | weather specialist / weather-heavy | 30 | 160 | https://polymarket.com/profile/0x1838cca016850ac7185a9b149fe7d0bd2d6629b4 |
| 23 |  | $38,787.58 | $1,074,084.53 | 3.611% | weather specialist / weather-heavy | 11 | 163 | https://polymarket.com/profile/0xaaec89fcb2ff14b335ddd738edf355ac07038dc8 |
| 24 |  | $37,107.72 | $385,980.00 | 9.614% | weather-heavy mixed | 1 | 4 | https://polymarket.com/profile/0x63a49a02c71d3a63f391878ec310dc81a524b5dc |
| 25 |  | $36,270.19 | $279,088.19 | 12.996% | weather specialist / weather-heavy | 0 | 29 | https://polymarket.com/profile/0x62d2bcd198bb6eab8b7eeb9d2061815dc02b9eb7 |

## Top weather-heavy actifs/récents

| # | handle | weather PnL | weather volume | PnL/vol | classification | active | recent | use | profile |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 |  | $23,469.62 | $797,544.25 | 2.943% | weather specialist / weather-heavy | 100 | 199 |  | https://polymarket.com/profile/0x906f2454a777600aea6c506247566decef82371a |
| 2 |  | $19,511.69 | $475,869.55 | 4.100% | weather specialist / weather-heavy | 100 | 199 |  | https://polymarket.com/profile/0x2b2866a724e73bf45af306036f12f20170b4d021 |
| 3 |  | $11,588.78 | $523,888.72 | 2.212% | weather specialist / weather-heavy | 98 | 200 |  | https://polymarket.com/profile/0x4ce3f17be91c3d0d6dbfed7bd4d326957dec4291 |
| 4 |  | $15,798.98 | $321,617.19 | 4.912% | weather specialist / weather-heavy | 100 | 197 |  | https://polymarket.com/profile/0xa37d1d1a3367c6ebc692e37c29bccb8bb015b2b4 |
| 5 |  | $14,775.84 | $698,335.84 | 2.116% | weather specialist / weather-heavy | 99 | 198 |  | https://polymarket.com/profile/0x5ea284bb13db26c76529a944e6bf9497c8c5e97f |
| 6 |  | $23,900.84 | $8,165,518.41 | 0.293% | weather specialist / weather-heavy | 95 | 200 |  | https://polymarket.com/profile/0x5f211a24da4c005d9438a1ea269673b85ed0b376 |
| 7 |  | $49,971.27 | $4,620,632.97 | 1.081% | weather specialist / weather-heavy | 96 | 198 |  | https://polymarket.com/profile/0x1f66796b45581868376365aef54b51eb84184c8d |
| 8 |  | $14,236.18 | $3,997,602.42 | 0.356% | weather specialist / weather-heavy | 93 | 197 |  | https://polymarket.com/profile/0xfbb7fc19f80b26152fc5886b5eafa7d437f26f27 |
| 9 |  | $121,335.48 | $8,835,337.51 | 1.373% | weather specialist / weather-heavy | 97 | 192 |  | https://polymarket.com/profile/0x594edb9112f526fa6a80b8f858a6379c8a2c1c11 |
| 10 |  | $15,370.50 | $603,901.57 | 2.545% | weather specialist / weather-heavy | 77 | 199 |  | https://polymarket.com/profile/0xf6f79fb0b579918f101bb6d0a264a492ce9de0da |
| 11 |  | $50,075.70 | $6,133,466.34 | 0.816% | weather specialist / weather-heavy | 63 | 180 |  | https://polymarket.com/profile/0xb40e89677d59665d5188541ad860450a6e2a7cc9 |
| 12 |  | $18,409.90 | $1,287,679.95 | 1.430% | weather specialist / weather-heavy | 35 | 200 |  | https://polymarket.com/profile/0x116db6298abcdefe06f9f5458c293c7de185fbf1 |
| 13 |  | $24,257.36 | $230,245.16 | 10.535% | weather specialist / weather-heavy | 28 | 200 |  | https://polymarket.com/profile/0x77266604e63f5caf08d19caebae0c563ce064aee |
| 14 |  | $12,478.30 | $191,555.84 | 6.514% | weather specialist / weather-heavy | 26 | 200 |  | https://polymarket.com/profile/0xad7b6b87daf99c08900763cc4f7842ee695680c9 |
| 15 |  | $17,814.47 | $518,865.38 | 3.433% | weather specialist / weather-heavy | 27 | 195 |  | https://polymarket.com/profile/0x8e22f7e80a03a36c80a7fe545369f008fc1e3061 |
| 16 |  | $12,943.18 | $3,031,522.48 | 0.427% | weather specialist / weather-heavy | 22 | 200 |  | https://polymarket.com/profile/0x50936370f48b7c7f87016ae8ec1462d0200a272c |
| 17 |  | $11,836.53 | $7,059,456.20 | 0.168% | weather specialist / weather-heavy | 22 | 200 |  | https://polymarket.com/profile/0xcbbc5e035504421b084ad9248b660f6e9618b5d0 |
| 18 |  | $15,985.48 | $397,949.96 | 4.017% | weather specialist / weather-heavy | 22 | 196 |  | https://polymarket.com/profile/0xaa7a74b8c754e8aacc1ac2dedb699af0a3224d23 |
| 19 |  | $30,684.46 | $1,713,245.93 | 1.791% | weather specialist / weather-heavy | 16 | 200 |  | https://polymarket.com/profile/0x6297b93ea37ff92a57fd636410f3b71ebf74517e |
| 20 |  | $45,558.18 | $3,188,650.65 | 1.429% | weather specialist / weather-heavy | 29 | 183 |  | https://polymarket.com/profile/0x57ee70867b4e387de9de34fd62bc685aa02a8112 |
| 21 |  | $16,049.09 | $1,363,281.89 | 1.177% | weather specialist / weather-heavy | 51 | 160 |  | https://polymarket.com/profile/0xb06a0eae498750ed0acac7e1f759f741c56e52f5 |
| 22 |  | $26,382.95 | $1,137,004.35 | 2.320% | weather specialist / weather-heavy | 10 | 199 |  | https://polymarket.com/profile/0x8278252ebbf354eca8ce316e680a0eaf02859464 |
| 23 |  | $20,471.53 | $761,303.60 | 2.689% | weather specialist / weather-heavy | 10 | 198 |  | https://polymarket.com/profile/0xbdcd1a99e6880b8146f61323dcb799bb5b243e9c |
| 24 |  | $23,284.68 | $421,149.94 | 5.529% | weather specialist / weather-heavy | 8 | 199 |  | https://polymarket.com/profile/0xf1faf3f6ad1e0264d6cbecc1a416e7c536be047d |
| 25 |  | $32,941.94 | $1,406,844.71 | 2.342% | weather specialist / weather-heavy | 28 | 175 |  | https://polymarket.com/profile/0x1c0f3e4c90a48e4dd93d0abcdf719a5a5f1599d0 |

## Comptes rentables qui matchent les marchés live

| # | handle | weather PnL | weather volume | PnL/vol | classification | markets | market ids | cities | profile |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Handsanitizer23 | $71,174.40 | $953,274.81 | 7.466% | weather specialist / weather-heavy | 4 | 2074350, 2064908, 2074360, 2064918 | Dallas | https://polymarket.com/profile/0x05e70727a2e2dcd079baa2ef1c0b88af06bb9641 |
| 2 | Poligarch | $50,120.07 | $6,119,248.26 | 0.819% | weather specialist / weather-heavy | 4 | 2065018, 2065028, 2074460, 2074470 | Hong Kong | https://polymarket.com/profile/0xb40e89677d59665d5188541ad860450a6e2a7cc9 |
| 3 | Maskache2 | $49,973.43 | $4,620,632.97 | 1.082% | weather specialist / weather-heavy | 4 | 2065018, 2065028, 2074460, 2074470 | Hong Kong | https://polymarket.com/profile/0x1f66796b45581868376365aef54b51eb84184c8d |
| 4 | HenryTheAtmoPhD | $45,563.27 | $3,187,575.00 | 1.429% | weather specialist / weather-heavy | 4 | 2065018, 2065028, 2074460, 2074470 | Hong Kong | https://polymarket.com/profile/0x57ee70867b4e387de9de34fd62bc685aa02a8112 |
| 5 | JoeTheMeteorologist | $44,964.15 | $2,101,735.48 | 2.139% | weather specialist / weather-heavy | 4 | 2065018, 2065028, 2074460, 2074470 | Hong Kong | https://polymarket.com/profile/0x1838cca016850ac7185a9b149fe7d0bd2d6629b4 |
| 6 | Shoemaker34 | $33,959.87 | $511,111.46 | 6.644% | weather specialist / weather-heavy | 4 | 2074350, 2064908, 2074360, 2064918 | Dallas | https://polymarket.com/profile/0x8093017f08d8492927eb3b43c8b87aeffe38b208 |
| 7 | protrade3 | $32,652.55 | $1,404,727.24 | 2.324% | weather specialist / weather-heavy | 4 | 2065018, 2065028, 2074460, 2074470 | Hong Kong | https://polymarket.com/profile/0x1c0f3e4c90a48e4dd93d0abcdf719a5a5f1599d0 |
| 8 | khalidakup | $29,585.79 | $1,994,067.63 | 1.484% | weather specialist / weather-heavy | 4 | 2074350, 2064908, 2074360, 2064918 | Dallas | https://polymarket.com/profile/0x97eb7ddf9139a3db0be99e81217e20546e219fbe |
| 9 | David32534 | $22,948.21 | $344,769.11 | 6.656% | weather specialist / weather-heavy | 4 | 2074350, 2064908, 2074360, 2064918 | Dallas | https://polymarket.com/profile/0x6e9108c47fe74fb241be7760d889315c3c39134e |
| 10 | Junhoo2 | $21,991.53 | $340,842.17 | 6.452% | weather specialist / weather-heavy | 4 | 2074350, 2064908, 2074360, 2064918 | Dallas | https://polymarket.com/profile/0x34eccd57d85a42273ea46d8699a2666ac600b7cf |

## Cartes marchés live

| # | market | city | date | action | blocker | verdict | matched | top accounts | next | source latest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2065018 | Hong Kong | April 26 | paper_trade_watch_direct_station | extreme_price | paper_micro | 5 | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, paper_micro_order_with_strict_limit_and_fill_tracking | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en |
| 2 | 2065028 | Hong Kong | April 26 | paper_trade_watch_direct_station | none | watch_or_paper | 5 | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, paper_order_with_limit_and_fill_tracking | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en |
| 3 | 2074350 | Dallas | April 27 | watch_only | missing_tradeable_quote | watch_or_paper | 5 | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL |
| 4 | 2074460 | Hong Kong | April 27 | watch_only | missing_tradeable_quote | watch_or_paper | 5 | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, wait_for_executable_depth | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en |
| 5 | 2064908 | Dallas | April 26 | watch_only | missing_tradeable_quote | watch_or_paper | 5 | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL |
| 6 | 2074470 | Hong Kong | April 27 | watch_only | missing_tradeable_quote | watch_or_paper | 5 | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, wait_for_executable_depth | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en |
| 7 | 2074360 | Dallas | April 27 | watch_only | missing_tradeable_quote | watch_or_paper | 5 | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL |
| 8 | 2064918 | Dallas | April 26 | watch_only | high_slippage_risk | watch_or_paper | 5 | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_tighter_spread | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL |

## Lecture opérateur

- Les comptes rentables globaux ne sont pas tous actionnables: certains sont généralistes/inactifs.
- Les marchés live utiles sont ceux des cartes ci-dessus: ils matchent des comptes weather-heavy rentables et ont une source directe.
- Blocage principal: `extreme_price` / `missing_tradeable_quote`; donc **paper/micro strict-limit uniquement**, pas sizing normal.
- Pour Hong Kong: suivre HKO direct/latest puis attendre l’extrait daily officiel avant de considérer la résolution finale.