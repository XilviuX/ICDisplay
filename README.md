# ICDisplay

Affiche les données Home Assistant sur un écran OLED **SH1107 128x128** branché en I2C sur un Raspberry Pi 4 tournant sous **Home Assistant OS**.

## Ce qui s'affiche

```
┌────────────────┐
│  loulous.lu    │
│────────────────│
│  ● EN LIGNE    │
│────────────────│
│ TEMP   HUMID   │
│ 21.3°C  48.0%  │
│────────────────│
│   14:32:07     │
│ □ □ ■          │
└────────────────┘
```

- Indicateur heartbeat pulsant (online/offline)
- Température et humidité intérieure moyenne
- Heure en temps réel avec secondes
- Animation d'activité en bas

---

## Étape 1 — Activer l'I2C sur HAOS

Éteins le Pi, retire la carte SD, insère-la dans ton Mac.

```bash
diskutil list
# Repère la partition hassos-boot (~64MB EFI), ex: disk6s1

sudo diskutil mount /dev/disk6s1
cd /Volumes/hassos-boot

echo -e "dtparam=i2c_vc=on\ndtparam=i2c_arm=on" >> config.txt
mkdir -p CONFIG/modules
echo "i2c-dev" >> CONFIG/modules/rpi-i2c.conf

sudo diskutil umount /dev/disk6s1
```

Réinsère la SD, démarre le Pi, **redémarre une seconde fois** pour que le module soit bien chargé.

---

## Étape 2 — Connexion physique de l'écran

Écran **4 PIN I2C** → GPIO du Pi 4 :

| Broche écran | GPIO Pi 4 | Pin physique |
|---|---|---|
| VCC | 3.3V | Pin 1 |
| GND | GND | Pin 6 |
| SCL | GPIO 3 | Pin 5 |
| SDA | GPIO 2 | Pin 3 |

> **Adresse I2C par défaut :** `0x3C`  
> Si ton écran ne répond pas, essaie `0x3D`.

---

## Étape 3 — Ajouter le repo dans Home Assistant

1. Dans HA : **Settings → Add-ons → Add-on Store**
2. Menu ⋮ → **Repositories**
3. Ajouter : `https://github.com/XilviuX/ICDisplay`
4. Rafraîchir → l'add-on **ICDisplay** apparaît

---

## Étape 4 — Configurer l'add-on

Dans l'onglet **Configuration** de l'add-on :

```yaml
ha_url: "http://172.16.137.11:8123"
ha_token: "VOTRE_TOKEN_ICI"
i2c_bus: 1
i2c_address: "0x3C"
sensor_temp: "sensor.temperature_interieure_moyenne"
sensor_humidity: "sensor.humidite_interieure_moyenne"
```

**Créer un token :** HA → Profil → Sécurité → Long-Lived Access Token

---

## Étape 5 — Démarrer

Onglet **Info** → **Start**. Consulte les logs pour vérifier.

Logs normaux au démarrage :
```
[ICDisplay] Connexion I2C bus=1 addr=0x3C
[ICDisplay] Démarrage du rendu...
```

---

## Dépannage

**L'écran reste noir :**
- Vérifie le câblage (VCC sur 3.3V, pas 5V)
- Essaie l'adresse `0x3D` dans la config
- Dans le terminal HAOS : `i2cdetect -y 1` pour scanner le bus

**"HORS LIGNE" s'affiche :**
- Vérifie que le token est correct
- Vérifie que `ha_url` est accessible depuis le Pi

**Erreur device `/dev/i2c-1` not found :**
- L'I2C n'est pas activé → refaire l'Étape 1
- Essaie un second redémarrage du Pi

---

## Structure du repo

```
ICDisplay/
├── repository.yaml          ← Déclaration du repo HAOS
└── icdisplay/
    ├── config.yaml          ← Métadonnées de l'add-on
    ├── Dockerfile           ← Image Docker Alpine + Python
    └── run.py               ← Script principal
```
