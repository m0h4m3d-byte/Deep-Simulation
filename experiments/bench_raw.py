from src.simulator import Simulator
from main import Agent
seeds=list(range(32))
total=[]
day1=[]
esc=[]
for s in seeds:
    sim=Simulator(seed=s)
    sim.reset()
    views=sim.step(None)
    ag=Agent()
    for t in range(24):
        a=ag(views[0])
        views=sim.step([a,{"farmer":["PASS"],"hands":[],"market":[]}])
    pc=sum(1 for row in views[0]["farms"][0]["tiles"] for t in row if isinstance(t,dict) and t.get("kind")=="PLANT")
    day1.append(pc)
    while not sim.done:
        a=ag(views[0])
        views=sim.step([a,{"farmer":["PASS"],"hands":[],"market":[]}])
    money=float(sim.state[0].observation.farms[0]["money"])
    total.append(money)
    ordered=ag.market.animals_ordered
    final=sim.state[0].observation.farms[0]["tiles"]
    present={"COW":0,"SHEEP":0,"GOOSE":0}
    for row in final:
        for c in row:
            if isinstance(c,dict) and "animal" in c and c["animal"] in present:
                present[c["animal"]]+=1
    esc.append(max(0,sum(ordered.values())-sum(present.values())))
print(f"day1 {day1}")
print(f"day1 avg {sum(day1)/len(day1):.1f}")
print(f"money mean {sum(total)/len(total):.0f} worst {min(total):.0f} best {max(total):.0f}")
print(f"escapes {esc} avg {sum(esc)/len(esc):.2f} cnt>0 {sum(1 for e in esc if e>0)}/32")
