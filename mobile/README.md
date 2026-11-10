# PactoBridge na Androida

PactoBridge odbiera prędkość z bieżni ZIPRO Pacto przez Bluetooth LE, a następnie
udostępnia ją w tej samej sieci Wi-Fi jako czujnik Running Speed and Cadence (RSC).
Zwift na komputerze z Windows widzi telefon jako **PactoBridge WiFi**.

## Wymagania

- Telefon Android 12 lub nowszy. Potwierdzonym urządzeniem jest Samsung Galaxy S22+
  (SM-S906B, Android 16).
- Komputer z Zwift i telefon połączone z tą samą siecią Wi-Fi/LAN.
- Włączony Bluetooth w telefonie.
- Bieżnia ZIPRO Pacto z wybudzoną konsolą.
- PactoBridge pozostaje otwarty na pierwszym planie podczas treningu.

Drugi telefon i Zwift Companion nie są potrzebne.

## Przygotowanie i trening

1. Otwórz PactoBridge. Odbiornik Wi-Fi uruchomi się automatycznie.
2. Przy bieżni naciśnij fizyczny **STOP**, wybudź konsolę i upewnij się, że pas
   całkowicie stoi oraz konsola pokazuje `0`.
3. Rozłącz iConsole+ — aplikacja producenta nie powinna być połączona z bieżnią.
4. W PactoBridge wybierz **Szukaj iConsole+0106**, a następnie wybierz bieżnię
   z listy.
5. Potwierdź oba pola: pas stoi, a operator jest przy fizycznym STOP.
6. Naciśnij **Przygotuj sesję Pacto na postoju**. Poczekaj na gotowy stan i
   rzeczywisty odczyt `0.0 km/h`.
7. W Zwift wybierz **BIEG → źródło prędkości → PactoBridge WiFi**. Szukaj ikony
   Wi-Fi/sieci, a nie czujnika Bluetooth.
8. START, zmianę prędkości i STOP wykonuj fizycznymi przyciskami konsoli.

Zwift może rozłączyć bezczynny czujnik sieciowy po około 10 sekundach. Dlatego
najpierw przygotuj bieżnię w aplikacji, a potem wybierz czujnik w Zwift.

## Ważne zasady obsługi

- Aplikacja nie wysyła polecenia uruchomienia silnika, zmiany prędkości, nachylenia
  ani zatrzymania pasa.
- Podczas przygotowania sesji wysyłane są wyłącznie zapisane komendy inicjalizacji
  potrzebne do rozpoczęcia odczytu. Sesję przygotowuj tylko na postoju, przy zerze.
- Zwift otrzymuje co 250 ms ostatnią prędkość odebraną z bieżni. Podczas przerw BLE
  wartość pozostaje stała; wiek pomiaru jest widoczny w aplikacji. Rozłączenie BLE
  lub zakończenie sesji kończy nadawanie i usuwa zapamiętany pomiar.
- Rozłączenie telefonu lub zamknięcie aplikacji nie zatrzymuje silnika. W razie
  potrzeby użyj fizycznego STOP na konsoli.
- Pozostań przy bieżni podczas jej pracy. Po treningu zatrzymaj ją na konsoli.

## Typowe problemy

**Nie widzę iConsole+0106**

Wybudź panel przyciskiem STOP, sprawdź Bluetooth, rozłącz aplikację iConsole+ i
wyszukaj bieżnię ponownie.

**Nie widzę PactoBridge WiFi w Zwift**

Sprawdź, czy telefon i komputer są w tej samej sieci lokalnej. Otwórz PactoBridge,
poczekaj na status gotowości Wi-Fi i odśwież listę źródeł prędkości w sekcji BIEG.

**Zwift łączy się, ale czujnik znika**

Przygotuj Pacto przed wyborem sensora w Zwift. Upewnij się też, że aplikacja
PactoBridge jest na pierwszym planie i telefon nie przełączył się na inną sieć.

**Przycisk przygotowania sesji jest nieaktywny**

Wybierz bieżnię, zaznacz oba potwierdzenia operatora i zaczekaj na gotowość
odbiornika Wi-Fi.

## Instalacja i budowanie

APK walidacyjny ARM64 powstaje w `dist/PactoBridge-S22Plus-validation.apk` po
uruchomieniu w PowerShell z katalogu głównego projektu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_android.ps1
```

Pakiet jest podpisany lokalnym kluczem debug i służy do instalacji testowej; nie
jest wydaniem Google Play. Szczegóły protokołu sieciowego opisuje
[NETWORK_PROTOCOL.md](NETWORK_PROTOCOL.md), a techniczny przebieg sesji
[SESSION_WORKFLOW.md](SESSION_WORKFLOW.md).

Diagnostyka sieci na komputerze znajduje się w
[`scripts/probe_android_wifi.py`](../scripts/probe_android_wifi.py). Domyślny tryb
sprawdza metadane. Opcja `--subscribe --duration 90` zapisuje rzeczywiste pomiary,
nie steruje bieżnią i wymaga uruchomionego źródła.

## Potwierdzona konfiguracja

Test end-to-end wykonano 10 listopada 2026 r. na Galaxy S22+ i Zwift Windows.
Komputer otrzymał rzeczywiste pomiary RSC przy prędkości około 1 km/h oraz zmienne
próbki od około 2,1 do 6,0 km/h. Zwift wybrał PactoBridge WiFi jako źródło Run
Speed, a operator potwierdził, że prędkość wyświetla się w grze. Potwierdzono też
fizyczny STOP i powrót telemetrii do zera.
