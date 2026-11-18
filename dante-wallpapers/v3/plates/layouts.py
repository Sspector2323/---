"""Раскладки окон: горизонтальный монитор (3 окна в ряд) и вертикальный (2 окна сверху + большое снизу).
ha — высота стрельчатой части окна; plaque — табличка под окном."""
import json


def land():
    wins, plaques = [], []
    for i in range(3):
        x = 24 + i * (608 + 24)
        wins.append({"x": x, "y": 24, "w": 608, "h": 880, "ha": 370})
        plaques.append({"cx": x + 304, "y": 918, "w": 400, "h": 140})
    return {"size": [1920, 1080], "wins": wins, "plaques": plaques, "outro": 1}


def port():
    wins = [{"x": 24, "y": 24, "w": 504, "h": 760, "ha": 306},
            {"x": 552, "y": 24, "w": 504, "h": 760, "ha": 306},
            {"x": 24, "y": 930, "w": 1032, "h": 780, "ha": 330}]
    plaques = [{"cx": 276, "y": 796, "w": 430, "h": 120}, {"cx": 804, "y": 796, "w": 430, "h": 120},
               {"cx": 540, "y": 1722, "w": 560, "h": 120}]
    return {"size": [1080, 1920], "wins": wins, "plaques": plaques, "outro": 2}


LAYOUTS = {"land": land(), "port": port()}

if __name__ == "__main__":
    json.dump(LAYOUTS, open("out/layouts.json", "w"), indent=1)
    print("ok")
