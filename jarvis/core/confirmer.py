"""Подтверждения опасных действий: голосом ИЛИ кнопкой на дашборде — что раньше."""
import threading
import uuid

YES = ("да", "подтверждаю", "давай", "выполняй", "конечно", "ок", "окей", "угу", "ага", "yes", "делай", "разрешаю")
NO = ("нет", "не", "отмена", "отмени", "стоп", "не надо", "запрещаю", "no")


class Confirmer:
    def __init__(self, io, voice_enabled: bool):
        self.io = io
        self.voice = voice_enabled
        self.pending: dict[str, dict] = {}
        self.lock = threading.Lock()

    def ask(self, question: str, timeout: float = 120) -> bool:
        cid = uuid.uuid4().hex[:8]
        item = {"q": question[:400], "event": threading.Event(), "answer": None}
        with self.lock:
            self.pending[cid] = item
        if self.voice:
            threading.Thread(target=self._by_voice, args=(cid, item), daemon=True).start()
        else:
            print(f"❓ Подтвердите на дашборде: {question[:200]}")
        item["event"].wait(timeout)
        with self.lock:
            self.pending.pop(cid, None)
        return item["answer"] is True

    def _by_voice(self, cid: str, item: dict):
        self.io.confirming = True
        try:
            self.io.say(f"Подтвердите: {item['q'][:200]}. Да или нет? Можно кнопкой на дашборде.")
            for _ in range(4):  # ~30 секунд слушаем, пока не ответят голосом или кнопкой
                if item["event"].is_set():
                    return
                heard = (self.io.listen(timeout=7, phrase_limit=4) or "").lower()
                if not heard:
                    continue
                print(f"🎤 Вы: {heard}")
                words = heard.replace(",", " ").split()
                if any(w in words for w in YES):
                    self.answer(cid, True)
                    return
                if any(w in words for w in NO) or "не надо" in heard:
                    self.answer(cid, False)
                    return
        finally:
            self.io.confirming = False

    def answer(self, cid: str, yes: bool) -> bool:
        with self.lock:
            item = self.pending.get(cid)
        if not item or item["event"].is_set():
            return False
        item["answer"] = yes
        item["event"].set()
        if self.voice:
            self.io.say("Принято." if yes else "Отменяю.", cache=True, quiet=True)
        return True

    def listing(self) -> list[dict]:
        with self.lock:
            return [{"id": k, "question": v["q"]} for k, v in self.pending.items() if not v["event"].is_set()]
