# Weather paper micro stress test

Spend actually filled in paper ledger: $39.0
forecast max bias [-2,-1,0,+1,+2] C x sigma [1.0,1.4,2.0,2.8] C

## Position robustness
- **ROBUST** Seoul April 26 NO 20°C higher: entry=0.28 filled=$2.24 baseP=0.858 baseEdge=0.578 good=19/20 worstEdge=0.0285 breakevenBias=2.3C
- **ROBUST** Beijing April 26 NO 25°C exact: entry=0.62 filled=$10.0 baseP=0.7815 baseEdge=0.1615 good=19/20 worstEdge=-0.0029 breakevenBias=-1.0C
- **ROBUST** Seoul April 27 NO 19°C exact: entry=0.82 filled=$5.0 baseP=0.9691 baseEdge=0.1491 good=17/20 worstEdge=-0.0617 breakevenBias=1.7C
- **ROBUST** Shanghai April 26 NO 23°C exact: entry=0.64 filled=$4.7552 baseP=0.7815 baseEdge=0.1415 good=19/20 worstEdge=-0.0229 breakevenBias=1.0C
- **ROBUST** Munich April 26 NO 19°C exact: entry=0.65 filled=$5.0 baseP=0.7815 baseEdge=0.1315 good=19/20 worstEdge=-0.0329 breakevenBias=-1.0C
- **MEDIUM** Munich April 26 NO 18°C exact: entry=0.71 filled=$10.0 baseP=0.8951 baseEdge=0.1851 good=18/20 worstEdge=-0.0929 breakevenBias=-2.0C
- **MEDIUM** Beijing April 26 NO 24°C exact: entry=0.82 filled=$2.0 baseP=0.8951 baseEdge=0.0751 good=14/20 worstEdge=-0.2029 breakevenBias=-3.3C

## Portfolio worst/best stress
- worst-ish bias=-1C sigma=1.0C EV=$9.26 (23.7%)
- worst-ish bias=-2C sigma=1.0C EV=$10.75 (27.6%)
- worst-ish bias=-1C sigma=1.4C EV=$11.51 (29.5%)
- worst-ish bias=-2C sigma=1.4C EV=$12.78 (32.8%)
- worst-ish bias=0C sigma=1.4C EV=$12.99 (33.3%)
- best-ish bias=1C sigma=1.4C EV=$14.27 (36.6%)
- best-ish bias=-2C sigma=2.0C EV=$14.59 (37.4%)
- best-ish bias=-1C sigma=2.8C EV=$14.68 (37.7%)
- best-ish bias=1C sigma=1.0C EV=$15.65 (40.1%)
- best-ish bias=-2C sigma=2.8C EV=$15.75 (40.4%)

## Rules
- Seoul April 26 NO 20°: keep_paper; can add only after refresh confirms source and book / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=2.3C
- Beijing April 26 NO 25°: keep_paper; can add only after refresh confirms source and book / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=-1.0C
- Seoul April 27 NO 19°: keep_paper; can add only after refresh confirms source and book / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=1.7C
- Shanghai April 26 NO 23°: keep_paper; can add only after refresh confirms source and book / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=1.0C
- Munich April 26 NO 19°: keep_paper; can add only after refresh confirms source and book / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=-1.0C
- Munich April 26 NO 18°: keep paper only, no add / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=-2.0C
- Beijing April 26 NO 24°: keep paper only, no add / adverse=forecast/source max moves toward the rejected outcome / breakeven bias=-3.3C