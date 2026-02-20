import time, random, os, re, unicodedata, asyncio, threading, msvcrt
from dotenv import load_dotenv

from colorama import just_fix_windows_console, Fore, Back, Style
from datetime import datetime
from telethon.sync import TelegramClient
from telethon.errors.rpcerrorlist import PeerFloodError, SessionPasswordNeededError, PasswordHashInvalidError, PhoneCodeInvalidError, PhoneNumberBannedError, FloodWaitError
from telethon.tl.types import InputPeerUser

load_dotenv()
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')

# Глобальный флаг для остановки рассылки
stop_flag = False

def clearConsole():
    os.system('cls' if os.name=='nt' else 'clear')

def check_stop_key():
    """Проверяет нажатие клавиши для остановки (Q или Esc)"""
    if msvcrt.kbhit():
        key = msvcrt.getch()
        if key in (b'q', b'Q', b'\x1b'):  # Q или Esc
            return True
    return False

class TGSpam:
    def __init__(self):
        self.api_id = api_id
        self.api_hash = api_hash
        self.accounts = self.readAccounts()
        self.last_account_index = -1  # Для кругового выбора аккаунтов
        self.repeat_count = 1  # По умолчанию 1 повторение

        self.logToFile("НАЧАЛО РАБОТЫ СКРИПТА\n\n")
        self.connect()
        self.mode = self.selectMode()
        if self.mode == '1':
            self.users = self.scrapeMembers(self.selectChat())
        else:
            self.users = self.readTargets()
        random.shuffle(self.users)
        self.spamMessages = self.getSpamMessages()
        random.shuffle(self.spamMessages)
        
        # Информация об остановке
        self.logMessageInfo("\n[Q] или [Esc] - остановить рассылку\n")
        
        self.spam(self.users, self.spamMessages)

    def readAccounts(self):
        accounts = []
        with open('TGAccounts.txt', 'r') as file:
            for line in file:
                phone_number = line.strip()
                account = {'phone': phone_number}
                accounts.append(account)
        return accounts

    def selectMode(self):
        clearConsole()
        self.logMessageInfo('Выберите режим работы:\n')
        self.logMessageWarning('1. Парсинг участников из чата')
        self.logMessageWarning('2. Рассылка по списку пользователей (targets.txt)')
        mode = self.logInput('\nВведите номер режима (1 или 2): ')
        
        clearConsole()
        repeat_input = self.logInput('Сколько раз повторять рассылку? (0 = бесконечно): ')
        try:
            self.repeat_count = int(repeat_input)
        except ValueError:
            self.repeat_count = 1
        
        return mode

    def readTargets(self):
        targets = []
        with open('targets.txt', 'r', encoding='utf-8') as file:
            for line in file:
                target = line.strip()
                if target:
                    targets.append(target)
        self.logMessageInfo(f"\nЗагружено {len(targets)} пользователей из targets.txt!")
        return targets

    def logToFile(self, text):
        with open("TGSpam.log", 'a', encoding='utf-8') as file:
            if "\n---\n" != text:
                date_time = datetime.now().strftime("[%Y.%m.%d %H:%M:%S]")
                file.write(f"{date_time} {text} \n")
            else:
                file.write(f"{text} \n")

    def logMessageInfo(self, text):
        print(Style.RESET_ALL + Style.BRIGHT + Fore.CYAN + text + Style.RESET_ALL)
        self.logToFile(text)

    def logMessageError(self, text):
        print(Style.RESET_ALL + Style.BRIGHT + Fore.RED + text + Style.RESET_ALL)
        self.logToFile(text)

    def logMessageWarning(self, text):
        print(Style.RESET_ALL + Style.BRIGHT + Fore.YELLOW + text + Style.RESET_ALL)
        self.logToFile(text)

    def logInput(self, text):
        return input(Style.RESET_ALL + Style.BRIGHT + Fore.GREEN + text + Style.RESET_ALL)
        self.logToFile(text)

    def сleanBadSymbols(self, txt):
        cleaned_name = re.sub(r'[<>:"/\\|?*]', '', txt)
        cleaned_name = ''.join(c for c in cleaned_name if unicodedata.category(c) != 'So')
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        return cleaned_name

    def checkAccount(self, account):
        try:
            account['tgClient'].send_message("SpamBot", "/start")
            time.sleep(1)
            lastMessageFromBot = account['tgClient'].get_messages("SpamBot", limit=1)[0].message
            
            # Проверяем можно ли писать неконтактам
            if "But I can't message non-contacts!" in lastMessageFromBot or \
               "Но я не могу писать неконтактам" in lastMessageFromBot or \
               "не могу писать" in lastMessageFromBot.lower():
                self.logMessageError(f"[{account['phone']}] Аккаунт не может писать неконтактам.")
                account['status'] = False
                return False
            
            # Проверяем по ключевым фразам (английский и русский)
            if ("Good news" in lastMessageFromBot and "free as a bird" in lastMessageFromBot) or \
               ("Ваш аккаунт свободен" in lastMessageFromBot):
                account['status'] = True;
                self.logMessageInfo(f"[{account['phone']}] Аккаунт не имеет ограничений.")
                return True
            else:
                self.logMessageError(f"[{account['phone']}] Аккаунт ограничен.")
                account['status'] = False;
                return False
        except FloodWaitError as e:
            wait_time = e.seconds
            self.logMessageError(f"[{account['phone']}] Ожидание {wait_time} сек. (SpamBot). Ставим паузу.")
            account['onPauseUntil'] = int(time.time()) + wait_time + 10
            return True  # Не блокируем аккаунт, просто пауза
        except PeerFloodError:
            self.logMessageError(f"[{account['phone']}] Аккаунт ограничен.")
            account['status'] = False;
            return False

    def checkVerificationCode(self, account):
        try:
            account['tgClient'].sign_in(account['phone'], self.logInput('Введите верификационый код: '))
        except PhoneCodeInvalidError:
            self.logMessageError(f"[{account['phone']}] Верификационый код не правильный.")
            self.checkVerificationCode(account)
        except SessionPasswordNeededError:
            self.check2FPassword(account)

    def check2FPassword(self, account):
        try:
            account['tgClient'].sign_in(password = self.logInput('Введите двуфакторный пароль: '))
        except PasswordHashInvalidError:
            self.logMessageError(f"[{account['phone']}] Двухфакторный пароль не правильный.")
            self.check2FPassword(account)


    def connect(self):
        for account in self.accounts:
            account['tgClient'] = TelegramClient(account['phone'], self.api_id, self.api_hash)
            account['exceptionsInARow'] = [];
            account['onPauseUntil'] = 0;
            account['status'] = True;
            account['tgClient'].connect()
            self.logMessageInfo(f"Подключения аккаунта с номером: {account['phone']}...")
            if not account['tgClient'].is_user_authorized():
                try:
                    account['tgClient'].send_code_request(account['phone'])
                except PhoneNumberBannedError:
                    self.logMessageError(f"[{account['phone']}] Аккаунт заблокирован")
                    account['status'] = False
                    account['tgClient'].disconnect()
                    self.logMessageInfo("\n---\n")
                    continue
                self.checkVerificationCode(account)

            self.checkAccount(account)
            self.logMessageInfo("\n---\n")
            # Не отключаем аккаунты, они понадобятся для рассылки

    def selectChat(self):
        clearConsole()
        self.accounts[0]['tgClient'].connect()
        groups = [dialog for dialog in self.accounts[0]['tgClient'].get_dialogs() if dialog.is_group and dialog.is_channel and dialog.entity.username]
        self.accounts[0]['tgClient'].disconnect()
        self.logMessageInfo('C какого чата вы бы хотели спарсить участников, что бы сразу начать на них рассылку:\n')
        [self.logMessageWarning(str(groups.index(group) + 1) + '. ' + self.сleanBadSymbols(group.title)) for group in groups]
        return self.selectChatInput(groups)
    
    def selectChatInput(self, groups):
        try:
            selectedChatIndex = int(self.logInput('\n\nВведите индекс чата подлежащий рассылки участникам выбранного чата: '))
            selectedDialogObject = groups[int(selectedChatIndex) - 1]
            return selectedDialogObject.entity.username
        except ValueError:
            self.logMessageError("Пожайлуста введите число, а не строку.")
            self.selectChatInput(groups)

    def scrapeMembers(self, selectedGroup):
        clearConsole()
        users = []
        for account in self.accounts:
            if account['status'] == True:
                self.logMessageWarning(f"[{account['phone']}] Парсит участников...")
                account['tgClient'].connect()
                for user in account['tgClient'].get_participants(selectedGroup, aggressive=False):
                    if self.accounts.index(account) == 0:
                        # Пропускаем ботов - им нельзя отправлять сообщения первыми
                        if user.bot:
                            continue
                        if user.username:
                            users.append({'type': 'username', 'value': user.username})
                        elif user.id:
                            # Сохраняем ID и access_hash для отправки через InputPeerUser
                            users.append({'type': 'peer', 'user_id': user.id, 'access_hash': user.access_hash})
                account['tgClient'].disconnect()
        self.logMessageInfo(f"\nПолучено {len(users)} участников!")
        self.logMessageInfo(f"Начинаем атаку")
        return users

    def getSpamMessages(self):
        with open("TGSpamText.txt", 'r', encoding='utf-8') as file:
            text = file.read()
        elements = text.split("\n^^^")
        return elements

    def selectAccount(self):
        workAccounts = []
        for account in self.accounts:
            if account['status'] == True and account['onPauseUntil'] <= int(time.time()):
                workAccounts.append(account);
        if not workAccounts:
            return None
        
        # Круговой выбор для равномерного распределения
        for i in range(len(self.accounts)):
            self.last_account_index = (self.last_account_index + 1) % len(self.accounts)
            account = self.accounts[self.last_account_index]
            if account['status'] == True and account['onPauseUntil'] <= int(time.time()):
                return account
        
        # Если круговой не сработал, возвращаем случайный
        return random.choice(workAccounts);

    def setException(self, phone, exceptIsset):
        for account in self.accounts:
            if account['phone'] == phone:
                if exceptIsset:  # Если ошибка
                    if(len(account['exceptionsInARow']) > 5):
                        account['exceptionsInARow'].pop(0);
                    account['exceptionsInARow'].append(exceptIsset)
                    if(account['exceptionsInARow'].count(True) == 6):
                        account['exceptionsInARow'] = [];
                        account['onPauseUntil'] = int(time.time()) + 120;
                else:  # Если успех — сбрасываем счетчик ошибок
                    account['exceptionsInARow'] = [];

    def disconnect_all(self):
        """Отключает все аккаунты"""
        for account in self.accounts:
            try:
                if 'tgClient' in account and account['tgClient'].is_connected():
                    account['tgClient'].disconnect()
                    print(f"[{account['phone']}] Аккаунт отключен")
            except:
                pass

    def spam(self, users, messages, delay=15):
        clearConsole()
        self.logMessageWarning(f"Начало атаки!\n\n")
        self.logMessageInfo("[Q] или [Esc] - остановить рассылку\n")

        # Проверяем доступные аккаунты перед началом
        available_accounts = [acc for acc in self.accounts if acc['status'] == True]
        if not available_accounts:
            self.logMessageError("Нет доступных аккаунтов для рассылки!")
            return

        # Проверяем есть ли пользователи для рассылки
        if not users:
            self.logMessageError("Нет пользователей для рассылки! Возможно, все участники чата - боты.")
            return

        self.logMessageInfo(f"Доступно аккаунтов: {len(available_accounts)}")
        self.logMessageInfo(f"Пользователей для рассылки: {len(users)}\n")

        repeat_info = "бесконечно" if self.repeat_count == 0 else f"{self.repeat_count} раз(а)"
        self.logMessageInfo(f"Повторений: {repeat_info}\n")

        iteration = 0
        while self.repeat_count == 0 or iteration < self.repeat_count:
            # Проверка на остановку в начале каждого повторения
            if check_stop_key():
                self.logMessageWarning("\n[!] Остановка рассылки пользователем...")
                break
                
            if iteration > 0:
                self.logMessageWarning(f"\n=== Повторение {iteration + 1} ===\n")
                time.sleep(1)  # Небольшая задержка перед стартом повторения

            iteration += 1

            for i, user in enumerate(users):
                # Проверка на остановку перед каждым пользователем
                if check_stop_key():
                    self.logMessageWarning("\n[!] Остановка рассылки пользователем...")
                    return
                    
                if i > 0:
                    time.sleep(delay)  # Задержка между пользователями

                # Отправляем все сообщения по очереди с задержкой 3 сек
                for msg_index, message in enumerate(messages):
                    # Проверка на остановку перед каждым сообщением
                    if check_stop_key():
                        self.logMessageWarning("\n[!] Остановка рассылки пользователем...")
                        return

                    sent_count = 0

                    # Отправляем сообщение со всех доступных аккаунтов одновременно
                    for account in self.accounts:
                        if account['status'] != True or account['onPauseUntil'] > int(time.time()):
                            continue

                        # Подключаем аккаунт если отключен
                        if not account['tgClient'].is_connected():
                            account['tgClient'].connect()

                        try:
                            self.logMessageWarning(f"[{account['phone']}] Попытка отправить сообщения пользователю {user}")
                            
                            # Определяем получателя в зависимости от типа
                            if isinstance(user, dict):
                                if user['type'] == 'username':
                                    recipient = user['value']
                                elif user['type'] == 'peer':
                                    recipient = InputPeerUser(user['user_id'], user['access_hash'])
                            else:
                                recipient = user  # Старый формат (просто строка)
                            
                            account['tgClient'].send_message(recipient, message)
                            self.logMessageInfo(f"[{account['phone']}] Сообщение отправлено")
                            sent_count += 1
                            self.setException(account['phone'], False)
                        except ValueError as e:
                            # Ошибка при парсинге получателя (например, бот)
                            error_msg = str(e)
                            if "bots cannot start conversations" in error_msg or "бот" in error_msg.lower():
                                self.logMessageError(f"[{account['phone']}] Это бот, пропускаем.")
                            else:
                                self.logMessageError(f"[{account['phone']}] Ошибка получателя: {e}")
                            self.setException(account['phone'], True)
                        except FloodWaitError as e:
                            wait_time = e.seconds
                            self.logMessageError(f"[{account['phone']}] Ожидание {wait_time} сек. Ставим паузу.")
                            account['onPauseUntil'] = int(time.time()) + wait_time + 10
                            self.setException(account['phone'], True)
                        except PeerFloodError:
                            self.logMessageError(f"[{account['phone']}] Аккаунт заблокирован (PeerFloodError).")
                            account['status'] = False
                            self.setException(account['phone'], True)
                        except Exception as e:
                            self.logMessageError(f"[{account['phone']}] Неизвестная ошибка: {e}")
                            self.setException(account['phone'], True)

                    if sent_count > 0:
                        self.logMessageInfo(f"[{user}] Отправлено с {sent_count} аккаунтов")

                    # Задержка 3 секунды между сообщениями (кроме последнего)
                    if msg_index < len(messages) - 1:
                        # Проверка на остановку во время задержки
                        for _ in range(30):  # Проверяем 30 раз по 0.1 сек
                            if check_stop_key():
                                self.logMessageWarning("\n[!] Остановка рассылки пользователем...")
                                return
                            time.sleep(0.1)


just_fix_windows_console()

# ---- ФИКС ДЛЯ PYTHON 3.13/3.14 ----
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
# ----------------------------------

tg_spam = None
try:
    tg_spam = TGSpam()
except KeyboardInterrupt:
    print(Style.RESET_ALL + Style.BRIGHT + Fore.YELLOW + "\n[!] Рассылка остановлена через Ctrl+C")
finally:
    # Отключаем все аккаунты при завершении
    if tg_spam:
        tg_spam.disconnect_all()
