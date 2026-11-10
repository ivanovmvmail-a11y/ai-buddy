import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { useDemo } from "@/lib/store";

beforeEach(() => {
  useDemo.getState().reset();
  useDemo.getState().setUser("intern-anya");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const login = (id: string) => fireEvent.change(screen.getByLabelText("Войти как"), { target: { value: id } });

describe("экран «план + чат»", () => {
  it("бот пишет первым: день, прогресс, следующий шаг", () => {
    render(<Home />);
    expect(screen.getByText(/2-й день стажировки/)).toBeTruthy();
    expect(screen.getByText(/Закрыто 1 из 10/)).toBeTruthy();
  });

  it("стажёр отмечает свой пункт — кнопка исчезает", () => {
    render(<Home />);
    const week1 = screen.getByRole("region", { name: "Неделя 1" });
    const before = within(week1).getAllByRole("button", { name: "Готово" }).length;
    act(() => within(week1).getAllByRole("button", { name: "Готово" })[0].click());
    expect(within(week1).queryAllByRole("button", { name: "Готово" })).toHaveLength(before - 1);
  });

  it("заявка: черновик → подтверждение → ждёт наставника → наставник одобряет", () => {
    render(<Home />);
    const week1 = screen.getByRole("region", { name: "Неделя 1" });
    const btns = within(week1).getAllByRole("button", { name: "Сделать за меня" });
    act(() => btns[btns.length - 1].click()); // пространство команды
    expect(screen.getByText(/Заявка на доступ · черновик/)).toBeTruthy();
    act(() => screen.getByRole("button", { name: "Подтвердить" }).click());
    expect(screen.getByText(/ушла на согласование: Пётр Волков/)).toBeTruthy();

    act(() => login("mentor-petr"));
    act(() => screen.getByRole("button", { name: "Одобрить" }).click());
    expect(screen.queryByRole("region", { name: "Ждут одобрения" })).toBeNull();
    expect(useDemo.getState().items.find((i) => i.id === "anya.w1.access-team")?.status).toBe("done");
  });

  it("базовые доступы выдаются сразу", () => {
    render(<Home />);
    const week1 = screen.getByRole("region", { name: "Неделя 1" });
    act(() => within(week1).getAllByRole("button", { name: "Сделать за меня" })[0].click());
    act(() => screen.getByRole("button", { name: "Подтвердить" }).click());
    expect(screen.getByText(/доступ к «Jira и Confluence» выдан/)).toBeTruthy();
  });

  it("отмена черновика ничего не создаёт", () => {
    render(<Home />);
    act(() => screen.getAllByRole("button", { name: "Сделать за меня" })[0].click());
    act(() => screen.getByRole("button", { name: "Отменить" }).click());
    expect(screen.getByText(/ничего не отправлено/)).toBeTruthy();
    expect(useDemo.getState().requests).toHaveLength(2);
  });

  it("наставник отклоняет с причиной", () => {
    useDemo.getState().setUser("mentor-maria");
    render(<Home />);
    act(() => screen.getByRole("button", { name: "Отклонить…" }).click());
    fireEvent.change(screen.getByPlaceholderText("Причина отказа"), { target: { value: "Сначала песочница" } });
    act(() => screen.getByRole("button", { name: "Отклонить" }).click());
    expect(screen.getByText(/Причина: Сначала песочница/)).toBeTruthy();
  });

  it("объяснение под уровень: Аня — новичок в Git, Иван — уверенно", () => {
    render(<Home />);
    const anyaRow = screen.getByText("Запросить доступ в пространство команды и изучить его").closest("li")!;
    act(() => within(anyaRow).getByRole("button", { name: "Объяснить" }).click());
    expect(screen.getByText(/только начинается/)).toBeTruthy();
    expect(screen.getByText(/Источник: 05-platform-sandbox.md/)).toBeTruthy();

    act(() => login("intern-ivan"));
    const ivanRow = screen.getByText("Запросить доступ в пространство команды и изучить его").closest("li")!;
    act(() => within(ivanRow).getByRole("button", { name: "Объяснить" }).click());
    expect(screen.getByText(/Ты в этой теме уверенно/)).toBeTruthy();
  });

  it("кнопка действия в приветствии открывает черновик", () => {
    render(<Home />);
    const chat = screen.getByText(/2-й день стажировки/).closest("div")!.parentElement!;
    act(() => within(chat).getByRole("button", { name: "Сделать за меня" }).click());
    expect(screen.getByText(/Заявка на доступ · черновик/)).toBeTruthy();
  });

  it("«Следующий день» — напоминание о зависшем пункте, один раз", () => {
    useDemo.getState().setUser("intern-ivan");
    render(<Home />);
    act(() => screen.getByRole("button", { name: "Следующий день" }).click());
    expect(screen.getAllByText(/🔔/)).toHaveLength(3); // конспект, заявка и пункт со сроком «до дня 8»
    act(() => screen.getByRole("button", { name: "Следующий день" }).click());
    expect(screen.getAllByText(/🔔/)).toHaveLength(3); // конспект, заявка и пункт со сроком «до дня 8»
    expect(screen.getByText(/Зависших пунктов нет/)).toBeTruthy();
    act(() => screen.getByRole("button", { name: "Сброс" }).click());
    expect(useDemo.getState().days["intern-ivan"]).toBe(8);
  });

  it("куратор видит планы всех, но ничего не отмечает", () => {
    useDemo.getState().setUser("curator-dmitry");
    render(<Home />);
    expect(screen.queryAllByRole("button", { name: "Готово" })).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Стажёр"), { target: { value: "intern-ivan" } });
    expect(screen.getByText("План: Иван Кузнецов")).toBeTruthy();
  });

  it("Иван: бот говорит, кого ждём", () => {
    useDemo.getState().setUser("intern-ivan");
    render(<Home />);
    expect(screen.getByText(/Ждём ответа \(Мария Орлова\)/)).toBeTruthy();
  });

  it("HR BP не видит планы", () => {
    useDemo.getState().setUser("hrbp-elena");
    render(<Home />);
    expect(screen.getByText(/для твоей роли недоступны/)).toBeTruthy();
  });

  it("переключатель «План / Чат» на узком экране", () => {
    render(<Home />);
    act(() => screen.getByRole("tab", { name: "Чат" }).click());
    expect(screen.getByRole("tab", { name: "Чат" }).getAttribute("aria-selected")).toBe("true");
  });

  it("свободный вопрос уходит в /chat от имени пользователя; при сбое — «Повторить»", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ reply: "Ответ модели", sources: [{ title: "Первые дни", url: null }] })));
    render(<Home />);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Как запустить сервис?" } });
    await act(async () => {
      fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!);
    });
    expect(screen.getByText(/Не получилось связаться/)).toBeTruthy();
    await act(async () => {
      screen.getByRole("button", { name: "Повторить" }).click();
    });
    expect(screen.getByText("Ответ модели")).toBeTruthy();
    const headers = fetchMock.mock.calls[1][1]?.headers as Record<string, string>;
    expect(headers["X-User-Id"]).toBe("intern-anya");
  });

  it("ошибка сервера показывает его сообщение", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Помощник временно недоступен." }), { status: 502 }),
    );
    render(<Home />);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Привет" } });
    await act(async () => {
      fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!);
    });
    expect(screen.getByText("Помощник временно недоступен.")).toBeTruthy();
  });
});
