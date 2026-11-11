import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;

beforeEach(() => {
  srv = installFakeServer();
  useSession.setState({ userId: "intern-anya", internPick: null });
  useChat.getState().reset([]);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function open(userId = "intern-anya") {
  useSession.setState({ userId, internPick: null });
  return render(
    <Providers>
      <Home />
    </Providers>,
  );
}
const login = (id: string) => fireEvent.change(screen.getByLabelText("Войти как"), { target: { value: id } });
const click = (el: HTMLElement) => act(async () => fireEvent.click(el));
const week1 = () => screen.findByRole("region", { name: "Неделя 1" });

describe("экран «план + чат» на API", () => {
  it("бот пишет первым: день, прогресс, следующий шаг", async () => {
    open();
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
    expect(screen.getByText(/Закрыто 1 из 10/)).toBeTruthy();
    expect(srv.calls.every((c) => c.user === "intern-anya")).toBe(true);
  });

  it("стажёр отмечает свой пункт — запрос на сервер и обновлённый план", async () => {
    open();
    const w1 = await week1();
    const before = within(w1).getAllByRole("button", { name: "Готово" }).length;
    await click(within(w1).getAllByRole("button", { name: "Готово" })[0]);
    await waitFor(() => expect(within(w1).queryAllByRole("button", { name: "Готово" })).toHaveLength(before - 1));
    expect(srv.calls.some((c) => c.method === "POST" && c.path.includes("/status"))).toBe(true);
  });

  it("ошибка отметки показывается у пункта", async () => {
    open();
    const w1 = await week1();
    srv.state.items.find((i) => i.id === "anya.w1.notes")!.owner_role = "mentor"; // сервер передумал
    const row = within(w1).getByText("Завести конспект встреч с наставником").closest("li")!;
    await click(within(row).getByRole("button", { name: "Готово" }));
    expect(await within(row).findByRole("alert")).toBeTruthy();
  });

  it("заявка: черновик → подтверждение → ждёт наставника → наставник одобряет", async () => {
    open();
    const w1 = await week1();
    const btns = within(w1).getAllByRole("button", { name: "Сделать за меня" });
    await click(btns[btns.length - 1]); // пространство команды
    expect(await screen.findByText(/Заявка на доступ · черновик/)).toBeTruthy();
    expect(srv.state.requests).toHaveLength(2); // без подтверждения ничего не создано
    await click(await screen.findByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText(/ушла на согласование: Пётр Волков/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/Ждём: Пётр Волков/)).toBeTruthy());

    act(() => login("mentor-petr"));
    await click(await screen.findByRole("button", { name: "Одобрить" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ждут одобрения" })).toBeNull());
    expect(srv.state.items.find((i) => i.id === "anya.w1.access-team")?.status).toBe("done");
  });

  it("базовые доступы выдаются сразу", async () => {
    open();
    const w1 = await week1();
    await click(within(w1).getAllByRole("button", { name: "Сделать за меня" })[0]);
    await click(await screen.findByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText(/доступ к «Jira и Confluence» выдан/)).toBeTruthy();
  });

  it("повторная заявка — понятная ошибка", async () => {
    srv.state.requests.push({ ...srv.state.requests[0], id: "REQ-9", intern_id: "intern-anya", resource_id: "base-access" });
    open();
    const w1 = await week1();
    await click(within(w1).getAllByRole("button", { name: "Сделать за меня" })[0]);
    await click(await screen.findByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText(/Не получилось: Заявка на этот ресурс уже есть/)).toBeTruthy();
    expect(screen.getByText("Не выполнено")).toBeTruthy();
  });

  it("отмена черновика ничего не создаёт", async () => {
    open();
    await click((await screen.findAllByRole("button", { name: "Сделать за меня" }))[0]);
    await click(await screen.findByRole("button", { name: "Отменить" }));
    expect(await screen.findByText(/ничего не отправлено/)).toBeTruthy();
    expect(srv.state.requests).toHaveLength(2);
  });

  it("наставник отклоняет с причиной", async () => {
    open("mentor-maria");
    await click(await screen.findByRole("button", { name: "Отклонить…" }));
    fireEvent.change(screen.getByPlaceholderText("Причина отказа"), { target: { value: "Сначала песочница" } });
    await click(screen.getByRole("button", { name: "Отклонить" }));
    expect(await screen.findByText(/Причина: Сначала песочница/)).toBeTruthy();
  });

  it("без ключа объяснение — сценарное, по уровню: Аня новичок в Git, Иван уверенно", async () => {
    open();
    const row = (await screen.findByText("Запросить доступ в пространство команды и изучить его")).closest("li")!;
    await waitFor(() => expect(within(row).getByText(/здесь помогу подробно/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/только начинается/)).toBeTruthy();
    expect(screen.getByText(/Источник: 05-platform-sandbox.md/)).toBeTruthy();
    expect(screen.getByText(/сценарный режим/)).toBeTruthy();

    act(() => login("intern-ivan"));
    const ivanRow = (await screen.findByText("Запросить доступ в пространство команды и изучить его")).closest("li")!;
    await click(within(ivanRow).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/Ты в этой теме уверенно/)).toBeTruthy();
  });

  it("без ключа объяснение записывается в события и его можно оценить", async () => {
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    await click(await screen.findByRole("button", { name: "Полезно" }));
    await waitFor(() => expect(srv.feedback).toEqual([{ answer_id: "ans_explain_anya.w1.notes", useful: true }]));
  });

  it("сбой записи события не мешает сценарному объяснению", async () => {
    srv.explainFails = true;
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/Объясни пункт «Завести конспект/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Полезно" })).toBeNull();
  });

  it("с моделью объяснение уходит вопросом в /chat", async () => {
    srv.provider = "gigachat";
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.queryByText(/сценарный режим/)).toBeNull());
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/health")).toBe(true));
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText("Ответ модели")).toBeTruthy();
    const chat = srv.calls.find((c) => c.path === "/chat")!;
    expect(JSON.stringify(chat.body)).toContain("Завести конспект");
  });

  it("кнопка действия в приветствии открывает черновик", async () => {
    open();
    const hello = (await screen.findByText(/2-й день стажировки/)).parentElement!;
    await click(within(hello).getByRole("button", { name: "Сделать за меня" }));
    expect(await screen.findByText(/Заявка на доступ · черновик/)).toBeTruthy();
  });

  it("Иван: кого ждём и напоминания при входе; «Напомнить позже»", async () => {
    open("intern-ivan");
    expect(await screen.findByText(/Ждём ответа \(Мария Орлова\)/)).toBeTruthy();
    const reminder = (await screen.findByText(/ждёт. Напомнить наставнику/)).parentElement!;
    await click(within(reminder).getByRole("button", { name: "Напомнить позже" }));
    expect(await screen.findByText("Хорошо, напомню завтра.")).toBeTruthy();
    expect(srv.calls.some((c) => c.path.endsWith("/snooze"))).toBe(true);
  });

  it("колокольчик (спека 301): число, «Открыть в чате», «Готово» убирает напоминание", async () => {
    open("intern-ivan");
    const bell = await screen.findByRole("button", { name: /Напоминания: \d/ });
    const count = Number(bell.getAttribute("aria-label")!.match(/\d+/)![0]);
    await click(bell);
    const dialog = screen.getByRole("dialog", { name: "Напоминания" });
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(count);
    const first = within(dialog).getAllByRole("listitem")[0];
    await click(within(first).getByRole("button", { name: "Готово" }));
    await waitFor(() => expect(srv.calls.some((c) => c.method === "POST" && c.path.endsWith("/done"))).toBe(true));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: count > 1 ? `Напоминания: ${count - 1}` : "Напоминаний нет" })).toBeTruthy(),
    );
    const before = useChat.getState().messages.length;
    if (count > 1) {
      await click(within(screen.getByRole("dialog")).getAllByRole("button", { name: "Открыть в чате" })[0]);
      expect(screen.queryByRole("dialog")).toBeNull();
      await waitFor(() => expect(useChat.getState().messages.length).toBe(before + 1));
    }
  });

  it("колокольчик: «Напомнить завтра», пусто, закрытие по Escape", async () => {
    open("intern-ivan");
    await click(await screen.findByRole("button", { name: /Напоминания: \d/ }));
    const items = within(screen.getByRole("dialog")).getAllByRole("listitem");
    for (const li of items) await click(within(li).getByRole("button", { name: "Напомнить завтра" }));
    expect(srv.calls.filter((c) => c.path.endsWith("/snooze"))).toHaveLength(items.length);
    expect(await screen.findByText(/Напоминаний нет — всё по плану/)).toBeTruthy();
    await act(async () => fireEvent.keyDown(document, { key: "Escape" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await click(screen.getByRole("button", { name: "Напоминаний нет" }));
    await act(async () => fireEvent.mouseDown(document.body));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("напоминание о просрочке ведёт к пункту", async () => {
    open("intern-ivan");
    const reminder = (await screen.findByText(/прошёл срок/)).parentElement!;
    await click(within(reminder).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/Объясни пункт «Завести конспект/)).toBeTruthy();
  });

  it("«Следующий день» и «Сброс»", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    await click(screen.getByRole("button", { name: "Следующий день" }));
    await waitFor(() => expect(srv.state.days["intern-anya"]).toBe(3));
    expect(await screen.findByText(/Зависших пунктов нет/)).toBeTruthy();
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
  });

  it("код-слово демо-кнопок: спрашивает один раз, запоминает, сообщает об ошибке", async () => {
    srv.demoKey = "маяк";
    sessionStorage.clear();
    const prompt = vi.spyOn(window, "prompt");
    open();
    await screen.findByText(/2-й день стажировки/);

    prompt.mockReturnValueOnce(null);
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Без код-слова демо-кнопки на этом сайте не работают.")).toBeTruthy();

    prompt.mockReturnValueOnce("не то");
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Код-слово не подошло.")).toBeTruthy();
    expect(srv.state.days["intern-anya"]).toBe(2);

    prompt.mockReturnValueOnce(" маяк ");
    await click(screen.getByRole("button", { name: "Следующий день" }));
    await waitFor(() => expect(srv.state.days["intern-anya"]).toBe(3));
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
    expect(prompt).toHaveBeenCalledTimes(3); // после верного код-слова больше не спрашивает
    prompt.mockRestore();
  });

  it("сбой демо-панели — сообщение", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
  });

  it("куратор видит планы всех, но ничего не отмечает", async () => {
    open("curator-dmitry");
    await screen.findByText(/План: Аня Смирнова/);
    expect(screen.queryAllByRole("button", { name: "Готово" })).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Стажёр"), { target: { value: "intern-ivan" } });
    expect(await screen.findByText("План: Иван Кузнецов")).toBeTruthy();
  });

  it("HR BP не видит планы", async () => {
    open("hrbp-elena");
    expect(await screen.findByText(/для твоей роли недоступны/)).toBeTruthy();
    expect(await screen.findByText(/Планы и профили стажёров тебе не показываю/)).toBeTruthy();
  });

  it("сервер недоступен — сообщение и «Повторить»", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => {
      throw new TypeError("Failed to fetch");
    });
    open();
    expect(await screen.findByText(/Не получилось загрузить план/, {}, { timeout: 4000 })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Повторить" }, { timeout: 4000 })).toBeTruthy();
  });

  it("сервер ответил не по контракту — понятная ошибка", async () => {
    srv.state.days["intern-anya"] = "два" as unknown as number;
    open();
    expect(await screen.findByText("Сервер ответил в неожиданном формате.", {}, { timeout: 4000 })).toBeTruthy();
  });

  it("переключатель «План / Чат» на узком экране", async () => {
    open();
    await click(screen.getByRole("tab", { name: "Чат" }));
    expect(screen.getByRole("tab", { name: "Чат" }).getAttribute("aria-selected")).toBe("true");
  });

  it("свободный вопрос: сбой → «Повторить» → ответ и черновик от модели", async () => {
    srv.chatReplies = ["fail", {
      reply: "Подготовил черновик",
      actions: [{ id: "act_x", user_id: "intern-anya", tool: "set_plan_item_status", title: "Пункт плана: сделано",
        params: {}, status: "pending", result: null, error: null }],
    }];
    open();
    await screen.findByText(/2-й день стажировки/);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Как запустить сервис?" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
    await click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByText("Подготовил черновик")).toBeTruthy();
    expect(screen.getByText("Черновик действия")).toBeTruthy();
    expect(screen.getByText(/Источник: Первые дни/)).toBeTruthy();
  });

  it("ошибка модели показывает текст сервера; подсказка-вопрос уходит в чат", async () => {
    srv.chatReplies = ["502"];
    open();
    await screen.findByText(/2-й день стажировки/);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Привет" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
    expect(await screen.findByText("Помощник временно недоступен.")).toBeTruthy();

    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    await click(await screen.findByRole("button", { name: "К кому идти, если не получается?" }));
    expect(await screen.findByText("Ответ модели")).toBeTruthy();
  });
});
