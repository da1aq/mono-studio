import os
import json
import requests
import psycopg2

from flask import Flask, render_template, request
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_CHAT_ID = "2093246580"

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
# ПОДКЛЮЧЕНИЕ К POSTGRESQL
# ============================================================

def get_db_connection():
    connection = psycopg2.connect(
        os.getenv("DATABASE_URL")
    )

    return connection
    )

    return connection


# ============================================================
# ГЛАВНАЯ СТРАНИЦА
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


# ============================================================
# СТРАНИЦА СТАТУСА ЗАЯВКИ
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
# API СТАТУСА ЗАЯВКИ
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
# ПОЛУЧЕНИЕ ЗАЯВКИ С САЙТА
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


    # ========================================================
    # 1. Сначала создаём заявку в PostgreSQL
    # ========================================================

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


    # ========================================================
    # 2. Формируем сообщение для администратора
    # ========================================================

    text = (
        "📩 Новая заявка!\n\n"
        f"ID заявки: {booking_id}\n\n"
        f"Имя: {name}\n"
        f"Телефон: {phone}\n"
        f"Услуга: {service}\n"
        f"Сообщение: {message}"
    )


    # ========================================================
    # 3. Кнопки Telegram
    # ========================================================

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


    # ========================================================
    # 4. Отправляем заявку администратору
    # ========================================================

    telegram_response = requests.post(
        SEND_MESSAGE_URL,
        data={
            "chat_id": BOT_CHAT_ID,
            "text": text,
            "reply_markup": json.dumps(reply_markup)
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


    # ========================================================
    # 5. Получаем ID сообщения Telegram
    # ========================================================

    telegram_message_id = (
        telegram_data["result"]["message_id"]
    )


    # ========================================================
    # 6. Сохраняем telegram_message_id в PostgreSQL
    # ========================================================

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


    # ========================================================
    # 7. Ссылка клиента на Telegram
    # ========================================================

    telegram_link = (
        f"https://t.me/MonoStudioAppBot?start={booking_id}"
    )


    return {
        "success": True,
        "booking_id": booking_id,
        "telegram_link": telegram_link
    }


# ============================================================
# TELEGRAM WEBHOOK
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


        # ====================================================
        # START
        # ====================================================

        if text.startswith("/start"):

            parts = text.split(
                maxsplit=1
            )

            booking_id = None

            if len(parts) == 2:
                booking_id = parts[1]


            # =================================================
            # ЕСЛИ ЭТО АДМИН
            # =================================================

            if str(chat_id) == BOT_CHAT_ID:

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


            # =================================================
            # КЛИЕНТ
            # =================================================

            print("Клиент открыл бота.")
            print("Telegram ID клиента:", chat_id)
            print("ID заявки:", booking_id)


            # =================================================
            # НЕТ ID ЗАЯВКИ
            # =================================================

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


            # =================================================
            # ПРИВЯЗЫВАЕМ КЛИЕНТА К ЗАЯВКЕ
            # =================================================

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


            # =================================================
            # ЕСЛИ ЗАЯВКА НАЙДЕНА
            # =================================================

            if updated_booking:

                print(
                    "Клиент привязан к заявке:",
                    updated_booking[0]
                )

                welcome_text = (
                    "👋 Здравствуйте!\n\n"
                    "Вы подключили уведомления "
                    "по своей заявке.\n\n"
                    "Когда заявка будет обработана, "
                    "мы отправим вам результат сюда."
                )


            # =================================================
            # ЕСЛИ ЗАЯВКА НЕ НАЙДЕНА
            # =================================================

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


        # ====================================================
        # ОПРЕДЕЛЯЕМ НОВЫЙ СТАТУС
        # ====================================================

        if action == "accept_booking":

            status = "accepted"

            result_text = "✅ Заявка принята"


        elif action == "reject_booking":

            status = "rejected"

            result_text = "❌ Заявка отклонена"


        else:

            return "OK"


        # ====================================================
        # ИЩЕМ ЗАЯВКУ ПО TELEGRAM MESSAGE ID
        # ====================================================

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

            return "OK"


        booking_id = booking_data[0]

        client_chat_id = booking_data[1]

        current_status = booking_data[2]


        # ====================================================
        # НЕ ДАЁМ ПОВТОРНО ОБРАБАТЫВАТЬ ЗАЯВКУ
        # ====================================================

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


        # ====================================================
        # ОБНОВЛЯЕМ СТАТУС
        # ====================================================

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


        # ====================================================
        # ОБНОВЛЯЕМ СООБЩЕНИЕ АДМИНА
        # ====================================================

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


        # ====================================================
        # УВЕДОМЛЕНИЕ КЛИЕНТУ
        # ====================================================

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


        # ====================================================
        # ОТВЕЧАЕМ TELEGRAM
        # ====================================================

        requests.post(
            ANSWER_CALLBACK_URL,
            data={
                "callback_query_id": callback_query["id"]
            }
        )


    return "OK"


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)