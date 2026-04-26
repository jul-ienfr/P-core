# Weather paper micro ticket plan

Paper plan only. Probabilities are crude station-forecast normal proxy, not calibrated historical station errors. Do not market-buy; use strict limits only. Account-consensus divergence is flagged, not ignored.

## Selected paper portfolio
1. **Seoul April 26 — NO 20°C higher**
   - station RKSI forecast max 18°C; prob=0.858; refreshed ask=0.27; edge=0.588
   - paper size $20; strict limit ≤ **0.2806**; fill5=0.2756 fill10=0.2806 fill20=0.2852
   - accounts=10 consensus=NO 17°C; flags=none; EV proxy=$41.15
   - Will the highest temperature in Seoul be 20°C or higher on April 26?
2. **London April 26 — NO 18°C exact**
   - station EGLC forecast max 18°C; prob=0.721; refreshed ask=0.51; edge=0.211
   - paper size $10; strict limit ≤ **0.5159**; fill5=0.51 fill10=0.5159 fill20=0.5334
   - accounts=11 consensus=NO 20°C; flags=none; EV proxy=$3.98
   - Will the highest temperature in London be 18°C on April 26?
3. **Munich April 26 — NO 18°C exact**
   - station EDDM forecast max 20°C; prob=0.8951; refreshed ask=0.71; edge=0.1851
   - paper size $10; strict limit ≤ **0.71**; fill5=0.71 fill10=0.71 fill20=0.71
   - accounts=11 consensus=NO 16°C; flags=none; EV proxy=$2.61
   - Will the highest temperature in Munich be 18°C on April 26?
4. **Beijing April 26 — NO 25°C exact**
   - station ZBAA forecast max 26°C; prob=0.7815; refreshed ask=0.62; edge=0.1615
   - paper size $10; strict limit ≤ **0.62**; fill5=0.62 fill10=0.62 fill20=0.6222
   - accounts=8 consensus=NO 22°C; flags=none; EV proxy=$2.6
   - Will the highest temperature in Beijing be 25°C on April 26?
5. **Seoul April 27 — NO 19°C exact**
   - station RKSI forecast max 16°C; prob=0.9691; refreshed ask=0.82; edge=0.1491
   - paper size $5; strict limit ≤ **0.82**; fill5=0.82 fill10=0.82 fill20=0.82
   - accounts=6 consensus=NO 15°C; flags=none; EV proxy=$0.91
   - Will the highest temperature in Seoul be 19°C on April 27?
6. **Shanghai April 26 — NO 23°C exact**
   - station ZSPD forecast max 22°C; prob=0.7815; refreshed ask=0.64; edge=0.1415
   - paper size $5; strict limit ≤ **0.6405**; fill5=0.6405 fill10=0.6452 fill20=0.6501
   - accounts=10 consensus=NO 21°C; flags=none; EV proxy=$1.1
   - Will the highest temperature in Shanghai be 23°C on April 26?
7. **Munich April 26 — NO 19°C exact**
   - station EDDM forecast max 20°C; prob=0.7815; refreshed ask=0.65; edge=0.1315
   - paper size $5; strict limit ≤ **0.65**; fill5=0.65 fill10=0.65 fill20=0.6513
   - accounts=11 consensus=NO 16°C; flags=none; EV proxy=$1.01
   - Will the highest temperature in Munich be 19°C on April 26?
8. **Beijing April 26 — NO 24°C exact**
   - station ZBAA forecast max 26°C; prob=0.8951; refreshed ask=0.82; edge=0.0751
   - paper size $2; strict limit ≤ **0.82**; fill5=0.82 fill10=0.82 fill20=0.82
   - accounts=8 consensus=NO 22°C; flags=none; EV proxy=$0.18
   - Will the highest temperature in Beijing be 24°C on April 26?

## Watch-only / degraded after refresh
- paper_candidate Ankara April 26 NO 20°C: ask=0.71 edge=0.0715 limit=0.71 flags=none
- paper_candidate Munich April 26 YES 21°C: ask=0.029 edge=0.3315 limit=0.0321 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Seoul April 26 YES 18°C: ask=0.067 edge=0.212 limit=0.0689 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Seoul April 26 YES 17°C: ask=0.011 edge=0.2075 limit=0.0185 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Seoul April 27 YES 15°C: ask=0.029 edge=0.1895 limit=0.0321 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Shanghai April 26 YES 21°C: ask=0.047 edge=0.1715 limit=0.0674 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Ankara April 26 YES 22°C: ask=0.079 edge=0.1395 limit=0.0797 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Seoul April 27 YES 16°C: ask=0.14 edge=0.139 limit=0.14 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Beijing April 26 YES 27°C: ask=0.09 edge=0.1285 limit=0.0931 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Shanghai April 27 YES 25°C: ask=0.09 edge=0.1285 limit=0.1101 flags=model_vs_profitable_account_consensus_side_divergence
- paper_candidate Ankara April 26 YES 23°C: ask=0.019 edge=0.123 limit=0.0235 flags=model_vs_profitable_account_consensus_side_divergence