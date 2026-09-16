const form = document.querySelector("form");

const telegramContainer =
    document.querySelector("#telegram-link-container");


form.addEventListener(
    "submit",
    async function (event) {

        event.preventDefault();


        const button =
            form.querySelector("button");


        button.disabled = true;

        button.textContent =
            "Отправка...";


        const formData =
            new FormData(form);


        try {

            const response =
                await fetch(
                    "/booking",
                    {
                        method: "POST",
                        body: formData
                    }
                );


            if (!response.ok) {
                throw new Error(
                    "Ошибка сервера"
                );
            }


            const result =
                await response.json();


            form.reset();


            button.textContent =
                "Заявка отправлена!";


            telegramContainer.innerHTML = `

                <div class="booking-result">


                    <div class="section-label">
                        Заявка отправлена
                    </div>


                    <h3>
                        Заявка №${result.booking_id}
                    </h3>


                    <p>
                        Мы получили вашу заявку
                        и обработаем её.
                    </p>


                    <div class="booking-status">
                        🕐 Ожидает обработки
                    </div>


                    <div class="booking-actions">


                        <a
                            class="telegram-button"
                            href="${result.telegram_link}"
                            target="_blank"
                        >
                            Получать статус в Telegram
                        </a>


                        <a
                            class="status-button"
                            href="/status/${result.booking_id}"
                            target="_blank"
                        >
                            Посмотреть статус заявки
                        </a>


                    </div>


                </div>

            `;


            setTimeout(
                function () {

                    button.disabled = false;

                    button.textContent =
                        "Отправить заявку";

                },
                3000
            );

        }


        catch (error) {

            console.log(error);


            button.disabled = false;

            button.textContent =
                "Ошибка. Попробуйте снова.";

        }

    }
);