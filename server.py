import os
import requests
import psycopg2

from flask import Flask, render_template, request
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_CHAT_ID = os.getenv("BOT_CHAT_ID", "2093246580")

DATABASE_URL = os.getenv("DATABASE_URL")
DB_PASSWORD = os.getenv("DB_PASSWORD")


SEND_MESSAGE_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
)

EDIT_MESSAGE_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
)

ANSWER_CALLBACK_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# ПОДКЛЮЧЕНИЕ К DATABASE
# ============================================================

def get_db_connection():

    if DATABASE_URL:
        connection = psycopg2.connect(
            DATABASE_URL
        )

    else:
        connection = psycopg2.connect(
            host="localhost",
            port=5432,
            database="mono_studio",
            user="postgres",
            password=DB_PASSWORD
        )

    return connection


# ============================================================
# СОЗДАНИЕ ТАБЛИЦЫ
# ============================================================

def init_db():

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            service TEXT NOT NULL,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            telegram_message_id INTEGER,
            client_chat_id BIGINT
        )
        """
    )

    connection.commit()

    cursor.close()
    connection.close()

    print("PostgreSQL: таблица bookings готова.")


# ============================================================
# ГЛАВНАЯ
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# СТРАНИЦА СТАТУСА
# ============================================================

@app.route("/status/<int:booking_id>")
def status(booking_id):

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            phone,
            service,
            message,
            status,
            telegram_message_id,
            client_chat_id
        FROM bookings
        WHERE id = %s
        """,
        (booking_id,)
    )

    booking_data = cursor.fetchone()

    cursor.close()
    connection.close()


    if booking_data is None:

        return "Заявка не найдена", 404


    booking = {
        "id": booking_data[0],
        "name": booking_data[1],
        "phone": booking_data[2],
        "service": booking_data[3],
        "message": booking_data[4],
        "status": booking_data[5],
        "telegram_message_id": booking_data[6],
        "client_chat_id": booking_data[7]
    }


    if booking["status"] == "new":

        status_text = "🕐 Ожидает обработки"

    elif booking["status"] == "accepted":

        status_text = "✅ Заявка принята"

    elif booking["status"] == "rejected":

        status_text = "❌ Заявка отклонена"

    else:

        status_text = "Статус неизвестен"


    return render_template(
        "status.html",
        booking=booking,
        status_text=status_text
    )


# ============================================================
# API СТАТУСА
# ============================================================

@app.route("/api/status/<int:booking_id>")
def api_status(booking_id):

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, status
        FROM bookings
        WHERE id = %s
        """,
        (booking_id,)
    )

    booking_data = cursor.fetchone()

    cursor.close()
    connection.close()


    if booking_data is None:

        return {
            "error": "Заявка не найдена"
        }, 404


    return {
        "id": booking_data[0],
        "status": booking_data[1]
    }


# ============================================================
# СОЗДАНИЕ ЗАЯВКИ
# ============================================================

@app.route("/booking", methods=["POST"])
def booking():

    name = request.form["name"]
    phone = request.form["phone"]
    service = request.form["service"]
    message = request.form.get("message", "")


    print("Новая заявка!")
    print("Имя:", name)
    print("Телефон:", phone)
    print("Услуга:", service)
    print("Сообщение:", message)


    # --------------------------------------------------------
    # Сохраняем заявку в PostgreSQL
    # --------------------------------------------------------

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO bookings
        (
            name,
            phone,
            service,
            message,
            status
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            'new'
        )
        RETURNING id
        """,
        (
            name,
            phone,
            service,
            message
        )
    )

    booking_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()


    # --------------------------------------------------------
    # Сообщение админу
    # --------------------------------------------------------

    text = (
        "📩 Новая заявка!\n\n"
        f"ID заявки: {booking_id}\n\n"
        f"Имя: {name}\n"
        f"Телефон: {phone}\n"
        f"Услуга: {service}\n"
        f"Сообщение: {message}"
    )


    # --------------------------------------------------------
    # Кнопки
    # --------------------------------------------------------

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Принять заявку",
                    "callback_data": "accept_booking"
                },
                {
                    "text": "❌ Отклонить заявку",
                    "callback_data": "reject_booking"
                }
            ]
        ]
    }


    # --------------------------------------------------------
    # Отправляем админу
    # --------------------------------------------------------

    telegram_response = requests.post(
        SEND_MESSAGE_URL,
        data={
            "chat_id": BOT_CHAT_ID,
            "text": text,
            "reply_markup": str(reply_markup).replace(
                "'",
                '"'
            )
        }
    )


    telegram_data = telegram_response.json()


    if not telegram_data.get("ok"):

        print(
            "Ошибка Telegram:",
            telegram_data
        )

        return {
            "success": False
        }, 500


    # --------------------------------------------------------
    # Получаем ID Telegram-сообщения
    # --------------------------------------------------------

    telegram_message_id = (
        telegram_data["result"]["message_id"]
    )


    # --------------------------------------------------------
    # Записываем Telegram message ID
    # --------------------------------------------------------

    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE bookings
        SET telegram_message_id = %s
        WHERE id = %s
        """,
        (
            telegram_message_id,
            booking_id
        )
    )

    connection.commit()

    cursor.close()
    connection.close()


    # --------------------------------------------------------
    # Ссылка клиента
    # --------------------------------------------------------

    telegram_link = (
        f"https://t.me/MonoStudioAppBot?start={booking_id}"
    )


    return {
        "success": True,
        "booking_id": booking_id,
        "telegram_link": telegram_link
    }


# ============================================================
# TELEGRAM
# ============================================================

@app.route("/telegram", methods=["POST"])
def telegram():

    data = request.json

    print("Telegram отправил данные:")
    print(data)


    # ========================================================
    # ОБЫЧНОЕ СООБЩЕНИЕ
    # ========================================================

    if "message" in data:

        telegram_message = data["message"]

        chat_id = telegram_message["chat"]["id"]

        text = telegram_message.get("text", "")


        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        if text.startswith("/start"):

            parts = text.split(
                maxsplit=1
            )

            booking_id = None

            if len(parts) == 2:

                booking_id = parts[1]


            # ------------------------------------------------
            # АДМИН
            # ------------------------------------------------

            if str(chat_id) == str(BOT_CHAT_ID):

                requests.post(
                    SEND_MESSAGE_URL,
                    data={
                        "chat_id": chat_id,
                        "text": (
                            "👋 Привет, админ!\n\n"
                            "Здесь будут появляться новые заявки."
                        )
                    }
                )

                return "OK"


            # ------------------------------------------------
            # КЛИЕНТ БЕЗ ID ЗАЯВКИ
            # ------------------------------------------------

            if booking_id is None:

                requests.post(
                    SEND_MESSAGE_URL,
                    data={
                        "chat_id": chat_id,
                        "text": (
                            "👋 Здравствуйте!\n\n"
                            "Чтобы подключить уведомления, "
                            "используйте ссылку из вашей заявки."
                        )
                    }
                )

                return "OK"


            # ------------------------------------------------
            # ПРИВЯЗЫВАЕМ TELEGRAM К ЗАЯВКЕ
            # ------------------------------------------------

            connection = get_db_connection()

            cursor = connection.cursor()

            cursor.execute(
                """
                UPDATE bookings
                SET client_chat_id = %s
                WHERE id = %s
                RETURNING id
                """,
                (
                    chat_id,
                    booking_id
                )
            )

            updated_booking = cursor.fetchone()

            connection.commit()

            cursor.close()
            connection.close()


            if updated_booking:

                welcome_text = (
                    "👋 Здравствуйте!\n\n"
                    "Вы подключили уведомления "
                    "по своей заявке.\n\n"
                    "Когда заявка будет обработана, "
                    "мы отправим вам результат сюда."
                )

                print(
                    "Клиент привязан к заявке:",
                    updated_booking[0]
                )

            else:

                welcome_text = (
                    "⚠️ Заявка не найдена.\n\n"
                    "Пожалуйста, используйте ссылку "
                    "из вашей заявки."
                )


            requests.post(
                SEND_MESSAGE_URL,
                data={
                    "chat_id": chat_id,
                    "text": welcome_text
                }
            )

            return "OK"


    # ========================================================
    # CALLBACK QUERY
    # ========================================================

    if "callback_query" in data:

        callback_query = data["callback_query"]

        callback_message_id = (
            callback_query["message"]["message_id"]
        )

        action = callback_query["data"]


        # ----------------------------------------------------
        # Определяем действие
        # ----------------------------------------------------

        if action == "accept_booking":

            status = "accepted"

            result_text = "✅ Заявка принята"

        elif action == "reject_booking":

            status = "rejected"

            result_text = "❌ Заявка отклонена"

        else:

            return "OK"


        # ----------------------------------------------------
        # Ищем заявку
        # ----------------------------------------------------

        connection = get_db_connection()

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                client_chat_id,
                status
            FROM bookings
            WHERE telegram_message_id = %s
            """,
            (callback_message_id,)
        )

        booking_data = cursor.fetchone()


        if booking_data is None:

            cursor.close()
            connection.close()

            requests.post(
                ANSWER_CALLBACK_URL,
                data={
                    "callback_query_id": callback_query["id"],
                    "text": "Заявка не найдена."
                }
            )

            return "OK"


        booking_id = booking_data[0]

        client_chat_id = booking_data[1]

        current_status = booking_data[2]


        # ----------------------------------------------------
        # Если уже обработана
        # ----------------------------------------------------

        if current_status != "new":

            cursor.close()
            connection.close()

            requests.post(
                ANSWER_CALLBACK_URL,
                data={
                    "callback_query_id": callback_query["id"],
                    "text": "Заявка уже обработана."
                }
            )

            return "OK"


        # ----------------------------------------------------
        # Обновляем статус
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE bookings
            SET status = %s
            WHERE id = %s
            """,
            (
                status,
                booking_id
            )
        )

        connection.commit()

        cursor.close()
        connection.close()


        # ----------------------------------------------------
        # Меняем сообщение админу
        # ----------------------------------------------------

        admin_chat_id = (
            callback_query["message"]["chat"]["id"]
        )

        message_id = callback_message_id

        old_text = (
            callback_query["message"]["text"]
        )

        new_text = (
            old_text
            + f"\n\n{result_text}"
        )


        requests.post(
            EDIT_MESSAGE_URL,
            data={
                "chat_id": admin_chat_id,
                "message_id": message_id,
                "text": new_text
            }
        )


        # ----------------------------------------------------
        # Уведомляем клиента
        # ----------------------------------------------------

        if client_chat_id is not None:

            requests.post(
                SEND_MESSAGE_URL,
                data={
                    "chat_id": client_chat_id,
                    "text": (
                        f"По вашей заявке №{booking_id} "
                        f"получен результат:\n\n"
                        f"{result_text}"
                    )
                }
            )


        # ----------------------------------------------------
        # Подтверждаем Telegram
        # ----------------------------------------------------

        requests.post(
            ANSWER_CALLBACK_URL,
            data={
                "callback_query_id": callback_query["id"]
            }
        )


    return "OK"


# ============================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ============================================================

init_db()


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=True
    )