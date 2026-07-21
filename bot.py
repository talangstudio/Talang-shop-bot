# ============================================================
#   TALANG SHOP BOT - Full Final Version
#   Discord Shop Bot System
# ============================================================

import discord
from discord.ext import commands
from discord import ui, ButtonStyle, Interaction, Embed, Color, PermissionOverwrite
import aiosqlite
import json
import os
import asyncio
import io
from datetime import datetime
from dotenv import load_dotenv

# ============================================================
# LOAD ENV & CONFIG
# ============================================================
load_dotenv()

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default = {
            "PREFIX": "!",
            "BOT_NAME": "TALANG SHOP",
            "OWNER_ROLE_NAME": "OWNER",
            "CURRENCY": "Rp",
            "CATEGORY_SHOP_ID": None,
            "CATEGORY_OWNER_PANEL_ID": None,
            "CATEGORY_TIKET_ID": None,
            "CHANNEL_OPEN_TIKET_ID": None,
            "CHANNEL_NOTIFIKASI_ID": None,
            "CHANNEL_REVIEW_ID": None,
            "CHANNEL_PRODUK_STORAGE_ID": None,
            "CHANNEL_PROGRES_TIKET_ID": None,
            "QRIS_IMAGE_URL": None
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

config = load_config()

# ============================================================
# BOT SETUP
# ============================================================
intents = discord.Intents.all()
bot = commands.Bot(
    command_prefix=config["PREFIX"],
    intents=intents,
    help_command=None
)

DB_FILE = "database.db"

# ============================================================
# DATABASE
# ============================================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS produk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama TEXT NOT NULL,
                harga INTEGER NOT NULL,
                stok INTEGER NOT NULL DEFAULT 0,
                file_message_id INTEGER,
                active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tiket (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tiket_number INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                kategori TEXT NOT NULL,
                channel_id INTEGER,
                produk_id INTEGER,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT,
                closed_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transaksi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tiket_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                produk_id INTEGER,
                produk_nama TEXT,
                total_harga INTEGER,
                status TEXT DEFAULT 'PENDING',
                bukti_message_id INTEGER,
                created_at TEXT,
                confirmed_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS review (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                tiket_id INTEGER,
                kategori TEXT,
                rating INTEGER,
                review_text TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tiket_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                counter INTEGER DEFAULT 0
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO tiket_counter (id, counter) VALUES (1, 0)"
        )
        await db.commit()

async def get_next_tiket_number():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE tiket_counter SET counter = counter + 1 WHERE id = 1"
        )
        await db.commit()
        async with db.execute(
            "SELECT counter FROM tiket_counter WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]

# ============================================================
# HELPERS
# ============================================================
def is_owner(member: discord.Member) -> bool:
    role_name = config["OWNER_ROLE_NAME"]
    return (
        any(r.name == role_name for r in member.roles)
        or member.guild_permissions.administrator
    )

def format_rupiah(amount: int) -> str:
    return f"Rp {amount:,}".replace(",", ".")

def get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def get_owner_role(guild: discord.Guild):
    return discord.utils.get(guild.roles, name=config["OWNER_ROLE_NAME"])

async def log_progres(
    guild: discord.Guild,
    tiket_number: int,
    user: discord.Member,
    kategori: str,
    status: str,
    detail: str = ""
):
    ch_id = config.get("CHANNEL_PROGRES_TIKET_ID")
    if not ch_id:
        return
    channel = guild.get_channel(int(ch_id))
    if not channel:
        return

    color_map = {
        "OPEN": Color.blue(),
        "MENUNGGU PEMBAYARAN": Color.yellow(),
        "BUKTI DIKIRIM": Color.orange(),
        "LUNAS": Color.green(),
        "PRODUK TERKIRIM": Color.green(),
        "SELESAI": Color.green(),
        "DITOLAK": Color.red(),
        "CLOSED": Color.dark_grey(),
    }
    emoji_map = {
        "OPEN": "🔵",
        "MENUNGGU PEMBAYARAN": "🟡",
        "BUKTI DIKIRIM": "🟠",
        "LUNAS": "🟢",
        "PRODUK TERKIRIM": "✅",
        "SELESAI": "✅",
        "DITOLAK": "🔴",
        "CLOSED": "⚫",
    }

    embed = Embed(
        title=f"📋 LOG TIKET #{tiket_number:04d}",
        color=color_map.get(status, Color.greyple()),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=user.mention, inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    embed.add_field(
        name="📊 Status",
        value=f"{emoji_map.get(status, '⚪')} {status}",
        inline=True
    )
    if detail:
        embed.add_field(name="📝 Detail", value=detail, inline=False)
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")
    await channel.send(embed=embed)

async def send_notifikasi(
    guild: discord.Guild,
    user: discord.Member,
    kategori: str,
    detail: str = ""
):
    ch_id = config.get("CHANNEL_NOTIFIKASI_ID")
    if not ch_id:
        return
    channel = guild.get_channel(int(ch_id))
    if not channel:
        return

    embed = Embed(
        title="🎉 TRANSAKSI / LAYANAN BERHASIL!",
        color=Color.gold(),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=user.mention, inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    if detail:
        embed.add_field(name="📝 Detail", value=detail, inline=False)
    embed.add_field(
        name="⭐ Terima Kasih!",
        value="Terima kasih sudah menggunakan layanan **TALANG SHOP**!",
        inline=False
    )
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")
    await channel.send(content="@everyone", embed=embed)

async def send_review_channel(
    guild: discord.Guild,
    user: discord.Member,
    kategori: str,
    rating: int,
    review_text: str
):
    ch_id = config.get("CHANNEL_REVIEW_ID")
    if not ch_id:
        return
    channel = guild.get_channel(int(ch_id))
    if not channel:
        return

    stars = "⭐" * rating + "☆" * (5 - rating)
    embed = Embed(
        title="📝 REVIEW BARU MASUK!",
        color=Color.gold(),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=user.mention, inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    embed.add_field(
        name=f"⭐ Rating ({rating}/5)",
        value=stars,
        inline=False
    )
    embed.add_field(
        name="💬 Review",
        value=f'"{review_text}"',
        inline=False
    )
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")
    await channel.send(content="@everyone", embed=embed)

# ============================================================
# VIEW: OPEN TIKET (Persistent)
# ============================================================
class OpenTiketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🎫 Open Tiket",
        style=ButtonStyle.blurple,
        custom_id="persistent_open_tiket"
    )
    async def open_tiket(self, interaction: Interaction, button: ui.Button):
        embed = Embed(
            title="📂 Pilih Kategori Tiket",
            description=(
                "Silakan pilih layanan yang kamu butuhkan:\n\n"
                "🛒 **Beli Produk** - Lihat & beli produk .rbxm\n"
                "🔧 **Fix System** - Perbaikan system\n"
                "🎨 **Custom System** - Request custom\n"
                "🗺️ **Jasa Buat Maps** - Pembuatan maps\n"
                "💬 **Konsultasi** - Tanya dengan staff"
            ),
            color=Color.blue()
        )
        await interaction.response.send_message(
            embed=embed,
            view=KategoriView(),
            ephemeral=True
        )

# ============================================================
# VIEW: PILIH KATEGORI
# ============================================================
class KategoriView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    async def create_tiket(self, interaction: Interaction, kategori: str):
        await interaction.response.defer(ephemeral=True)

        guild  = interaction.guild
        user   = interaction.user
        cat_id = config.get("CATEGORY_TIKET_ID")

        if not cat_id:
            await interaction.followup.send(
                "❌ Category tiket belum diset! Minta OWNER jalankan `!setchannel`.",
                ephemeral=True
            )
            return

        category = guild.get_channel(int(cat_id))
        if not category:
            await interaction.followup.send(
                "❌ Category tiket tidak ditemukan!", ephemeral=True
            )
            return

        # Cek tiket aktif
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT channel_id FROM tiket WHERE user_id=? AND status NOT IN ('CLOSED')",
                (user.id,)
            ) as cur:
                existing = await cur.fetchone()

        if existing:
            ch = guild.get_channel(int(existing[0])) if existing[0] else None
            msg = f"❌ Kamu sudah punya tiket aktif!"
            if ch:
                msg += f" Silakan selesaikan di {ch.mention}"
            await interaction.followup.send(msg, ephemeral=True)
            return

        tiket_number = await get_next_tiket_number()
        ch_name      = f"tiket-{user.name.lower().replace(' ','-')}-{tiket_number:04d}"

        owner_role = await get_owner_role(guild)
        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            user: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
                embed_links=True
            ),
            guild.me: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True
            ),
        }
        if owner_role:
            overwrites[owner_role] = PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True
            )

        tiket_ch = await guild.create_text_channel(
            name=ch_name,
            category=category,
            overwrites=overwrites
        )

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """INSERT INTO tiket
                   (tiket_number, user_id, username, kategori, channel_id, status, created_at)
                   VALUES (?,?,?,?,?,'OPEN',?)""",
                (tiket_number, user.id, user.name, kategori, tiket_ch.id, get_timestamp())
            )
            await db.commit()

        await log_progres(guild, tiket_number, user, kategori, "OPEN")

        # Welcome embed
        wel = Embed(
            title=f"🎫 TIKET #{tiket_number:04d}",
            description=f"Selamat datang {user.mention}! Tiket kamu telah dibuat.",
            color=Color.blue(),
            timestamp=datetime.now()
        )
        wel.add_field(name="📂 Kategori", value=kategori, inline=True)
        wel.add_field(name="👤 Member",   value=user.mention, inline=True)
        wel.add_field(name="📊 Status",   value="🔵 OPEN", inline=True)
        if owner_role:
            wel.add_field(
                name="👮 Staff",
                value=f"Tim {owner_role.mention} akan segera membantu.",
                inline=False
            )
        wel.set_footer(text=f"TALANG SHOP • #{tiket_number:04d}")
        await tiket_ch.send(embed=wel)

        if kategori == "Beli Produk":
            await show_products(tiket_ch, user, tiket_number)
        else:
            svc = Embed(
                title=f"📂 {kategori}",
                description=(
                    "Silakan jelaskan kebutuhan kamu secara detail.\n"
                    "Staff **OWNER** akan segera merespon.\n\n"
                    "⏳ Mohon tunggu..."
                ),
                color=Color.blue()
            )
            await tiket_ch.send(embed=svc)
            await tiket_ch.send(
                embed=Embed(
                    description="🔧 **Panel Kontrol Tiket** (Hanya OWNER)",
                    color=Color.dark_grey()
                ),
                view=ServiceControlView(tiket_number, user.id, kategori)
            )

        await interaction.followup.send(
            f"✅ Tiket berhasil dibuat! Silakan cek {tiket_ch.mention}",
            ephemeral=True
        )

    @ui.button(label="🛒 Beli Produk",      style=ButtonStyle.green,  custom_id="kat_beli",   row=0)
    async def beli(self, i: Interaction, b: ui.Button):
        await self.create_tiket(i, "Beli Produk")

    @ui.button(label="🔧 Fix System",       style=ButtonStyle.blurple, custom_id="kat_fix",    row=0)
    async def fix(self, i: Interaction, b: ui.Button):
        await self.create_tiket(i, "Fix System")

    @ui.button(label="🎨 Custom System",    style=ButtonStyle.blurple, custom_id="kat_custom", row=1)
    async def custom(self, i: Interaction, b: ui.Button):
        await self.create_tiket(i, "Custom System")

    @ui.button(label="🗺️ Jasa Buat Maps",  style=ButtonStyle.blurple, custom_id="kat_maps",   row=1)
    async def maps(self, i: Interaction, b: ui.Button):
        await self.create_tiket(i, "Jasa Buat Maps")

    @ui.button(label="💬 Konsultasi",       style=ButtonStyle.grey,   custom_id="kat_konsul", row=2)
    async def konsul(self, i: Interaction, b: ui.Button):
        await self.create_tiket(i, "Konsultasi dengan Staff")

# ============================================================
# FUNGSI: TAMPILKAN PRODUK DI TIKET
# ============================================================
async def show_products(channel, user, tiket_number):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, nama, harga, stok FROM produk WHERE active=1 ORDER BY id"
        ) as cur:
            products = await cur.fetchall()

    header = Embed(
        title="🛒 KATALOG PRODUK - TALANG SHOP",
        description=(
            "Berikut adalah daftar produk yang tersedia.\n"
            "Klik tombol **🛒 Beli** pada produk yang kamu inginkan."
        ),
        color=Color.gold()
    )
    header.set_footer(text="TALANG SHOP • Katalog Produk")
    await channel.send(embed=header)

    if not products:
        await channel.send(
            embed=Embed(
                description="❌ Belum ada produk yang tersedia saat ini.",
                color=Color.red()
            )
        )
        await channel.send(
            embed=Embed(
                description="🔧 **Panel Kontrol Tiket** (Hanya OWNER)",
                color=Color.dark_grey()
            ),
            view=ServiceControlView(tiket_number, user.id, "Beli Produk")
        )
        return

    for prod in products:
        prod_id, nama, harga, stok = prod
        ada = stok > 0
        emb = Embed(
            title=f"📦 {nama}",
            color=Color.green() if ada else Color.red()
        )
        emb.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
        emb.add_field(
            name="📊 Stok",
            value=str(stok) if ada else "**HABIS ❌**",
            inline=True
        )
        view = BuyProductView(prod_id, nama, harga, stok, tiket_number) if ada else None
        await channel.send(embed=emb, view=view)

    await channel.send("─" * 35)
    await channel.send(
        embed=Embed(
            description="🔧 **Panel Kontrol Tiket** (Hanya OWNER)",
            color=Color.dark_grey()
        ),
        view=ServiceControlView(tiket_number, user.id, "Beli Produk")
    )

# ============================================================
# VIEW: TOMBOL BELI PRODUK
# ============================================================
class BuyProductView(ui.View):
    def __init__(self, prod_id, nama, harga, stok, tiket_number):
        super().__init__(timeout=None)
        self.prod_id      = prod_id
        self.nama         = nama
        self.harga        = harga
        self.stok         = stok
        self.tiket_number = tiket_number

        btn = ui.Button(
            label=f"🛒 Beli",
            style=ButtonStyle.green,
            custom_id=f"buy_{prod_id}_{tiket_number}"
        )
        btn.callback = self.buy_cb
        self.add_item(btn)

    async def buy_cb(self, interaction: Interaction):
        # Cek stok terbaru
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT stok FROM produk WHERE id=? AND active=1", (self.prod_id,)
            ) as cur:
                row = await cur.fetchone()

        if not row or row[0] <= 0:
            await interaction.response.send_message(
                "❌ Maaf, produk ini sudah **habis**!", ephemeral=True
            )
            return

        # Cek apakah sudah ada transaksi aktif di tiket ini
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                """SELECT t.id FROM transaksi t
                   JOIN tiket tk ON t.tiket_id = tk.id
                   WHERE tk.tiket_number=? AND t.status NOT IN ('PRODUK TERKIRIM','DITOLAK')""",
                (self.tiket_number,)
            ) as cur:
                existing_trx = await cur.fetchone()

        if existing_trx:
            await interaction.response.send_message(
                "❌ Kamu sudah memilih produk! Selesaikan transaksi yang berjalan dulu.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Disable semua tombol beli
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        # Detail pesanan
        order_emb = Embed(
            title="🧾 DETAIL PESANAN",
            color=Color.gold(),
            timestamp=datetime.now()
        )
        order_emb.add_field(name="📦 Produk", value=self.nama,                  inline=True)
        order_emb.add_field(name="💰 Total",  value=format_rupiah(self.harga),  inline=True)
        order_emb.add_field(
            name="💳 Cara Bayar",
            value=(
                "1. Scan QRIS di bawah ini\n"
                f"2. Transfer sebesar **{format_rupiah(self.harga)}**\n"
                "3. Kirim **foto/screenshot bukti pembayaran** di channel ini"
            ),
            inline=False
        )
        order_emb.set_footer(text=f"TALANG SHOP • Tiket #{self.tiket_number:04d}")
        await interaction.channel.send(embed=order_emb)

        # QRIS
        qris_url = config.get("QRIS_IMAGE_URL")
        if qris_url:
            qris_emb = Embed(title="📱 SCAN QRIS UNTUK MEMBAYAR", color=Color.blue())
            qris_emb.set_image(url=qris_url)
            await interaction.channel.send(embed=qris_emb)

        await interaction.channel.send(
            f"📸 {interaction.user.mention} silakan kirim **bukti pembayaran** kamu.\n"
            f"⏳ Menunggu bukti pembayaran... *(timeout: 30 menit)*"
        )

        # Simpan transaksi ke DB
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number=?", (self.tiket_number,)
            ) as cur:
                tk_row = await cur.fetchone()
            tk_id = tk_row[0] if tk_row else None

            await db.execute(
                """INSERT INTO transaksi
                   (tiket_id, user_id, produk_id, produk_nama, total_harga, status, created_at)
                   VALUES (?,?,?,?,?,'MENUNGGU PEMBAYARAN',?)""",
                (tk_id, interaction.user.id, self.prod_id,
                 self.nama, self.harga, get_timestamp())
            )
            await db.execute(
                "UPDATE tiket SET produk_id=?, status='MENUNGGU PEMBAYARAN' WHERE tiket_number=?",
                (self.prod_id, self.tiket_number)
            )
            await db.commit()

        await log_progres(
            interaction.guild, self.tiket_number, interaction.user,
            "Beli Produk", "MENUNGGU PEMBAYARAN",
            f"Produk: {self.nama} | Total: {format_rupiah(self.harga)}"
        )

        # Tunggu bukti bayar
        await wait_payment_proof(
            interaction.channel,
            interaction.user,
            self.prod_id,
            self.nama,
            self.harga,
            self.tiket_number
        )

# ============================================================
# FUNGSI: TUNGGU BUKTI PEMBAYARAN
# ============================================================
async def wait_payment_proof(channel, user, prod_id, nama, harga, tiket_number):
    def check(m):
        return (
            m.channel.id == channel.id
            and m.author.id == user.id
            and len(m.attachments) > 0
        )

    try:
        msg = await bot.wait_for("message", check=check, timeout=1800)

        bukti_emb = Embed(
            title="📸 BUKTI PEMBAYARAN DITERIMA",
            description="Menunggu konfirmasi dari **OWNER**...",
            color=Color.orange(),
            timestamp=datetime.now()
        )
        bukti_emb.add_field(name="👤 Member",  value=user.mention,            inline=True)
        bukti_emb.add_field(name="📦 Produk",  value=nama,                    inline=True)
        bukti_emb.add_field(name="💰 Total",   value=format_rupiah(harga),    inline=True)
        bukti_emb.set_image(url=msg.attachments[0].url)
        bukti_emb.set_footer(text=f"TALANG SHOP • Tiket #{tiket_number:04d}")

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number=?", (tiket_number,)
            ) as cur:
                tk_row = await cur.fetchone()
            tk_id = tk_row[0] if tk_row else None

            await db.execute(
                "UPDATE transaksi SET status='BUKTI DIKIRIM', bukti_message_id=? WHERE tiket_id=?",
                (msg.id, tk_id)
            )
            await db.execute(
                "UPDATE tiket SET status='BUKTI DIKIRIM' WHERE tiket_number=?",
                (tiket_number,)
            )
            await db.commit()

        await log_progres(
            channel.guild, tiket_number, user,
            "Beli Produk", "BUKTI DIKIRIM",
            f"Produk: {nama}"
        )

        owner_role = await get_owner_role(channel.guild)
        notif_text = f"{owner_role.mention if owner_role else ''} Ada bukti pembayaran baru! Mohon dikonfirmasi."

        await channel.send(
            content=notif_text,
            embed=bukti_emb,
            view=PaymentConfirmView(prod_id, nama, harga, tiket_number, user)
        )

    except asyncio.TimeoutError:
        timeout_emb = Embed(
            title="⏰ WAKTU HABIS",
            description=(
                f"{user.mention} Waktu pembayaran telah habis **(30 menit)**.\n"
                "Silakan buat tiket baru jika masih ingin membeli."
            ),
            color=Color.red()
        )
        await channel.send(embed=timeout_emb)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE tiket SET status='TIMEOUT' WHERE tiket_number=?",
                (tiket_number,)
            )
            await db.commit()

# ============================================================
# VIEW: KONFIRMASI PEMBAYARAN (OWNER ONLY)
# ============================================================
class PaymentConfirmView(ui.View):
    def __init__(self, prod_id, nama, harga, tiket_number, buyer: discord.Member):
        super().__init__(timeout=None)
        self.prod_id      = prod_id
        self.nama         = nama
        self.harga        = harga
        self.tiket_number = tiket_number
        self.buyer        = buyer

    def _disable_all(self):
        for item in self.children:
            item.disabled = True

    @ui.button(label="✅ Konfirmasi Bayar", style=ButtonStyle.green, custom_id="confirm_pay_btn")
    async def confirm(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Hanya **OWNER** yang bisa konfirmasi pembayaran!", ephemeral=True
            )
            return

        await interaction.response.defer()
        self._disable_all()
        await interaction.message.edit(view=self)

        # Update DB
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number=?", (self.tiket_number,)
            ) as cur:
                tk_row = await cur.fetchone()
            tk_id = tk_row[0] if tk_row else None

            await db.execute(
                "UPDATE transaksi SET status='LUNAS', confirmed_at=? WHERE tiket_id=?",
                (get_timestamp(), tk_id)
            )
            await db.execute(
                "UPDATE tiket SET status='LUNAS' WHERE tiket_number=?",
                (self.tiket_number,)
            )
            await db.execute(
                "UPDATE produk SET stok = MAX(0, stok - 1) WHERE id=?",
                (self.prod_id,)
            )
            await db.commit()

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            "Beli Produk", "LUNAS",
            f"Produk: {self.nama} | Dikonfirmasi: {interaction.user.mention}"
        )

        ok_emb = Embed(
            title="✅ PEMBAYARAN DIKONFIRMASI!",
            description=(
                f"Pembayaran **{format_rupiah(self.harga)}** telah dikonfirmasi "
                f"oleh {interaction.user.mention}.\n\n"
                "⏳ Memproses pengiriman produk..."
            ),
            color=Color.green(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=ok_emb)

        # Kirim produk
        await send_product_to_ticket(
            interaction.channel,
            interaction.guild,
            self.buyer,
            self.prod_id,
            self.nama,
            self.harga,
            self.tiket_number
        )

    @ui.button(label="❌ Tolak", style=ButtonStyle.red, custom_id="reject_pay_btn")
    async def reject(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Hanya **OWNER** yang bisa menolak pembayaran!", ephemeral=True
            )
            return

        modal = RejectModal(self.tiket_number, self.nama, self.buyer)
        await interaction.response.send_modal(modal)

        self._disable_all()
        await interaction.message.edit(view=self)

# ============================================================
# FUNGSI: KIRIM PRODUK KE TIKET
# ============================================================
async def send_product_to_ticket(
    channel, guild, buyer, prod_id, nama, harga, tiket_number
):
    storage_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
    if not storage_id:
        await channel.send("❌ Channel `produk-storage` belum diset!")
        return

    storage_ch = guild.get_channel(int(storage_id))
    if not storage_ch:
        await channel.send("❌ Channel `produk-storage` tidak ditemukan!")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT file_message_id FROM produk WHERE id=?", (prod_id,)
        ) as cur:
            row = await cur.fetchone()

    if not row or not row[0]:
        await channel.send("❌ File produk tidak ditemukan di database!")
        return

    try:
        file_msg = await storage_ch.fetch_message(int(row[0]))
        if not file_msg.attachments:
            await channel.send("❌ File tidak ditemukan di pesan storage!")
            return

        attachment  = file_msg.attachments[0]
        file_bytes  = await attachment.read()

        prod_emb = Embed(
            title="📦 PRODUK BERHASIL DIKIRIM!",
            description=f"File **{nama}** sudah kamu terima. Selamat menikmati! 🎉",
            color=Color.green(),
            timestamp=datetime.now()
        )
        prod_emb.add_field(name="📎 File",       value=attachment.filename,      inline=True)
        prod_emb.add_field(name="💰 Total Bayar", value=format_rupiah(harga),    inline=True)
        prod_emb.set_footer(text=f"TALANG SHOP • Tiket #{tiket_number:04d}")

        await channel.send(embed=prod_emb)
        await channel.send(
            file=discord.File(
                fp=io.BytesIO(file_bytes),
                filename=attachment.filename
            )
        )

        # Update DB
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number=?", (tiket_number,)
            ) as cur:
                tk_row = await cur.fetchone()
            tk_id = tk_row[0] if tk_row else None

            await db.execute(
                "UPDATE tiket SET status='PRODUK TERKIRIM' WHERE tiket_number=?",
                (tiket_number,)
            )
            await db.execute(
                "UPDATE transaksi SET status='PRODUK TERKIRIM' WHERE tiket_id=?",
                (tk_id,)
            )
            await db.commit()

        await log_progres(
            guild, tiket_number, buyer,
            "Beli Produk", "PRODUK TERKIRIM",
            f"Produk: {nama} | File: {attachment.filename}"
        )

        await send_notifikasi(
            guild, buyer, "Beli Produk",
            f"Produk: **{nama}** | Total: **{format_rupiah(harga)}**"
        )

        # Minta rating
        rating_emb = Embed(
            title="⭐ BERIKAN RATING & REVIEW",
            description=(
                f"{buyer.mention} Terima kasih sudah berbelanja di **TALANG SHOP**! 🎉\n\n"
                "Silakan berikan rating untuk layanan kami:"
            ),
            color=Color.gold()
        )
        await channel.send(
            embed=rating_emb,
            view=RatingView(tiket_number, "Beli Produk", buyer)
        )

    except discord.NotFound:
        await channel.send(
            "❌ Pesan file di `produk-storage` tidak ditemukan! "
            "Mungkin sudah dihapus. Hubungi OWNER."
        )
    except Exception as e:
        await channel.send(f"❌ Gagal mengirim produk: `{e}`")

# ============================================================
# MODAL: ALASAN TOLAK
# ============================================================
class RejectModal(ui.Modal, title="Alasan Penolakan"):
    reason = ui.TextInput(
        label="Alasan Penolakan",
        placeholder="Contoh: Bukti tidak jelas / Nominal tidak sesuai",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300
    )

    def __init__(self, tiket_number, nama, buyer):
        super().__init__()
        self.tiket_number = tiket_number
        self.nama         = nama
        self.buyer        = buyer

    async def on_submit(self, interaction: Interaction):
        rej_emb = Embed(
            title="❌ PEMBAYARAN DITOLAK",
            color=Color.red(),
            timestamp=datetime.now()
        )
        rej_emb.add_field(name="📦 Produk",      value=self.nama,               inline=True)
        rej_emb.add_field(name="❌ Ditolak oleh", value=interaction.user.mention, inline=True)
        rej_emb.add_field(name="📝 Alasan",       value=self.reason.value,       inline=False)
        rej_emb.add_field(
            name="ℹ️ Info",
            value="Silakan ulangi pembayaran atau hubungi OWNER.",
            inline=False
        )
        await interaction.response.send_message(
            content=self.buyer.mention,
            embed=rej_emb
        )

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """UPDATE transaksi SET status='DITOLAK'
                   WHERE tiket_id=(SELECT id FROM tiket WHERE tiket_number=?)""",
                (self.tiket_number,)
            )
            await db.execute(
                "UPDATE tiket SET status='DITOLAK' WHERE tiket_number=?",
                (self.tiket_number,)
            )
            await db.commit()

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            "Beli Produk", "DITOLAK",
            f"Alasan: {self.reason.value}"
        )

# ============================================================
# VIEW: RATING (1–5 BINTANG)
# ============================================================
class RatingView(ui.View):
    def __init__(self, tiket_number, kategori, buyer: discord.Member):
        super().__init__(timeout=None)
        self.tiket_number = tiket_number
        self.kategori     = kategori
        self.buyer        = buyer

        for i in range(1, 6):
            btn = ui.Button(
                label="⭐" * i,
                style=ButtonStyle.grey,
                custom_id=f"rate_{tiket_number}_{i}",
                row=0
            )
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, rating: int):
        async def callback(interaction: Interaction):
            if interaction.user.id != self.buyer.id:
                await interaction.response.send_message(
                    "❌ Hanya pembuat tiket yang bisa memberikan rating!",
                    ephemeral=True
                )
                return
            await interaction.response.send_modal(
                ReviewModal(self.tiket_number, self.kategori, self.buyer, rating)
            )
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        return callback

# ============================================================
# MODAL: TULIS REVIEW
# ============================================================
class ReviewModal(ui.Modal, title="✍️ Tulis Review Kamu"):
    review_text = ui.TextInput(
        label="Review",
        placeholder="Tulis pengalaman kamu menggunakan layanan TALANG SHOP...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, tiket_number, kategori, buyer, rating):
        super().__init__()
        self.tiket_number = tiket_number
        self.kategori     = kategori
        self.buyer        = buyer
        self.rating       = rating

    async def on_submit(self, interaction: Interaction):
        stars = "⭐" * self.rating + "☆" * (5 - self.rating)

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number=?", (self.tiket_number,)
            ) as cur:
                tk_row = await cur.fetchone()
            tk_id = tk_row[0] if tk_row else None

            await db.execute(
                """INSERT INTO review
                   (user_id, username, tiket_id, kategori, rating, review_text, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (self.buyer.id, self.buyer.name, tk_id,
                 self.kategori, self.rating, self.review_text.value, get_timestamp())
            )
            await db.commit()

        thx_emb = Embed(
            title="✅ Review Berhasil Dikirim!",
            color=Color.gold(),
            timestamp=datetime.now()
        )
        thx_emb.add_field(name=f"⭐ Rating ({self.rating}/5)", value=stars, inline=False)
        thx_emb.add_field(name="💬 Review", value=f'"{self.review_text.value}"', inline=False)
        thx_emb.set_footer(text="TALANG SHOP • Terima kasih atas reviewnya!")
        await interaction.response.send_message(embed=thx_emb)

        await send_review_channel(
            interaction.guild, self.buyer,
            self.kategori, self.rating, self.review_text.value
        )

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            self.kategori, "SELESAI",
            f"Rating: {self.rating}/5 | Review diberikan"
        )

# ============================================================
# VIEW: KONTROL TIKET (OWNER: Selesai + Close)
# ============================================================
class ServiceControlView(ui.View):
    def __init__(self, tiket_number, buyer_id, kategori):
        super().__init__(timeout=None)
        self.tiket_number = tiket_number
        self.buyer_id     = buyer_id
        self.kategori     = kategori

    @ui.button(
        label="✅ Tandai Selesai",
        style=ButtonStyle.green,
        custom_id="svc_done_btn"
    )
    async def selesai(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Hanya **OWNER** yang bisa menandai tiket selesai!", ephemeral=True
            )
            return

        await interaction.response.defer()

        buyer = interaction.guild.get_member(self.buyer_id)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE tiket SET status='SELESAI' WHERE tiket_number=?",
                (self.tiket_number,)
            )
            await db.commit()

        done_emb = Embed(
            title="✅ LAYANAN SELESAI!",
            description=(
                f"Tiket **#{self.tiket_number:04d}** telah diselesaikan oleh "
                f"{interaction.user.mention}."
            ),
            color=Color.green(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=done_emb)

        if buyer:
            await send_notifikasi(
                interaction.guild, buyer, self.kategori,
                f"Layanan **{self.kategori}** telah selesai!"
            )
            await log_progres(
                interaction.guild, self.tiket_number, buyer,
                self.kategori, "SELESAI",
                f"Diselesaikan oleh: {interaction.user.mention}"
            )

            rating_emb = Embed(
                title="⭐ BERIKAN RATING & REVIEW",
                description=(
                    f"{buyer.mention} Terima kasih sudah menggunakan layanan **TALANG SHOP**! 🎉\n\n"
                    "Silakan berikan rating untuk layanan kami:"
                ),
                color=Color.gold()
            )
            await interaction.channel.send(
                embed=rating_emb,
                view=RatingView(self.tiket_number, self.kategori, buyer)
            )

        button.disabled = True
        await interaction.message.edit(view=self)

    @ui.button(
        label="🔒 Close Tiket",
        style=ButtonStyle.red,
        custom_id="svc_close_btn"
    )
    async def close(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Hanya **OWNER** yang bisa menutup tiket!", ephemeral=True
            )
            return

        await interaction.response.defer()

        buyer = interaction.guild.get_member(self.buyer_id)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE tiket SET status='CLOSED', closed_at=? WHERE tiket_number=?",
                (get_timestamp(), self.tiket_number)
            )
            await db.commit()

        if buyer:
            await log_progres(
                interaction.guild, self.tiket_number, buyer,
                self.kategori, "CLOSED",
                f"Ditutup oleh: {interaction.user.mention}"
            )

        close_emb = Embed(
            title="🔒 TIKET DITUTUP",
            description=(
                f"Tiket **#{self.tiket_number:04d}** ditutup oleh {interaction.user.mention}.\n"
                "Channel akan dihapus dalam **5 detik**..."
            ),
            color=Color.dark_grey(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=close_emb)
        await asyncio.sleep(5)

        try:
            await interaction.channel.delete(
                reason=f"Tiket #{self.tiket_number:04d} ditutup oleh {interaction.user}"
            )
        except discord.errors.NotFound:
            pass

# ============================================================
# COMMANDS: SETUP EMBED OPEN TIKET
# ============================================================
@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def cmd_setup(ctx):
    ch_id = config.get("CHANNEL_OPEN_TIKET_ID")
    if not ch_id:
        await ctx.send("❌ Channel `open-tiket` belum diset! Jalankan `!setchannel` dulu.")
        return

    channel = ctx.guild.get_channel(int(ch_id))
    if not channel:
        await ctx.send("❌ Channel `open-tiket` tidak ditemukan!")
        return

    emb = Embed(
        title="🎫 TALANG SHOP — TICKET SYSTEM",
        description=(
            "Selamat datang di **TALANG SHOP**! 🛒\n\n"
            "Klik tombol **🎫 Open Tiket** di bawah untuk membuka tiket.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛒 **Beli Produk** — Beli file .rbxm\n"
            "🔧 **Fix System** — Perbaikan system\n"
            "🎨 **Custom System** — Request custom\n"
            "🗺️ **Jasa Buat Maps** — Pembuatan maps\n"
            "💬 **Konsultasi** — Tanya dengan staff\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ Tiket akan otomatis dibuat & hanya terlihat oleh kamu dan staff."
        ),
        color=Color.gold()
    )
    emb.set_footer(text="TALANG SHOP • Klik tombol di bawah untuk memulai")

    await channel.send(embed=emb, view=OpenTiketView())
    await ctx.send(f"✅ Embed tiket berhasil dikirim ke {channel.mention}!")

    try:
        await ctx.message.delete()
    except:
        pass

# ============================================================
# COMMANDS: SET CHANNEL
# ============================================================
@bot.command(name="setchannel")
@commands.has_permissions(administrator=True)
async def cmd_setchannel(ctx):
    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send(
        embed=Embed(
            title="⚙️ SETUP CHANNEL — TALANG SHOP",
            description=(
                "Saya akan menanyakan channel & category satu per satu.\n"
                "**Mention channel** dengan `#nama-channel`\n"
                "**Ketik ID** untuk category\n"
                "Ketik `skip` untuk melewati.\n\n"
                "Siap? Mari mulai! ⬇️"
            ),
            color=Color.blue()
        )
    )
    await asyncio.sleep(1)

    channel_fields = [
        ("CHANNEL_OPEN_TIKET_ID",    "🎫 Channel **#open-tiket**",      "mention channel"),
        ("CHANNEL_NOTIFIKASI_ID",    "🔔 Channel **#notifikasi**",       "mention channel"),
        ("CHANNEL_REVIEW_ID",        "⭐ Channel **#review**",           "mention channel"),
        ("CHANNEL_PRODUK_STORAGE_ID","📦 Channel **#produk-storage**",   "mention channel"),
        ("CHANNEL_PROGRES_TIKET_ID", "📊 Channel **#progres-tiket**",    "mention channel"),
    ]

    category_fields = [
        ("CATEGORY_SHOP_ID",        "🛒 Category **SHOP**",         "ketik ID category"),
        ("CATEGORY_OWNER_PANEL_ID", "🔒 Category **OWNER PANEL**",  "ketik ID category"),
        ("CATEGORY_TIKET_ID",       "📁 Category **TIKET AKTIF**",  "ketik ID category"),
    ]

    # Set channels
    for key, label, hint in channel_fields:
        await ctx.send(f"📝 {label} ({hint}):")
        try:
            msg = await bot.wait_for("message", check=chk, timeout=60)
            if msg.content.lower() == "skip":
                await ctx.send(f"⏭️ Dilewati.")
                continue
            if msg.channel_mentions:
                config[key] = msg.channel_mentions[0].id
                save_config(config)
                await ctx.send(f"✅ {label} → {msg.channel_mentions[0].mention}")
            else:
                await ctx.send("❌ Harus mention channel! Contoh: `#open-tiket`")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Jalankan `!setchannel` ulang.")
            return

    # Set categories
    for key, label, hint in category_fields:
        await ctx.send(
            f"📝 {label} ({hint}):\n"
            f"💡 Cara: Klik kanan category → **Copy ID** (aktifkan Developer Mode dulu)"
        )
        try:
            msg = await bot.wait_for("message", check=chk, timeout=60)
            if msg.content.lower() == "skip":
                await ctx.send(f"⏭️ Dilewati.")
                continue
            try:
                cat_id  = int(msg.content.strip())
                cat_obj = ctx.guild.get_channel(cat_id)
                if cat_obj and isinstance(cat_obj, discord.CategoryChannel):
                    config[key] = cat_id
                    save_config(config)
                    await ctx.send(f"✅ {label} → **{cat_obj.name}**")
                else:
                    await ctx.send(f"❌ ID tidak valid atau bukan category!")
            except ValueError:
                await ctx.send("❌ Masukkan angka ID!")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Jalankan `!setchannel` ulang.")
            return

    await ctx.send(
        embed=Embed(
            title="✅ SETUP CHANNEL SELESAI!",
            description=(
                "Semua channel & category sudah dikonfigurasi.\n\n"
                "Langkah selanjutnya:\n"
                "1. `!setqris` — Upload gambar QRIS\n"
                "2. `!addproduk` — Tambah produk\n"
                "3. `!setup` — Aktifkan embed open tiket"
            ),
            color=Color.green()
        )
    )

# ============================================================
# COMMANDS: SET QRIS
# ============================================================
@bot.command(name="setqris")
@commands.has_permissions(administrator=True)
async def cmd_setqris(ctx):
    await ctx.send(
        embed=Embed(
            title="📱 SET QRIS",
            description="Upload **gambar QRIS** kamu atau kirim **URL gambar**:",
            color=Color.blue()
        )
    )

    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=chk, timeout=60)
        url = None

        if msg.attachments:
            url = msg.attachments[0].url
        elif msg.content.startswith("http"):
            url = msg.content.strip()

        if url:
            config["QRIS_IMAGE_URL"] = url
            save_config(config)
            emb = Embed(
                title="✅ QRIS Berhasil Diset!",
                color=Color.green()
            )
            emb.set_image(url=url)
            await ctx.send(embed=emb)
        else:
            await ctx.send("❌ Upload gambar atau kirim URL yang valid!")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")

# ============================================================
# COMMANDS: TAMBAH PRODUK
# ============================================================
@bot.command(name="addproduk")
@commands.has_permissions(administrator=True)
async def cmd_addproduk(ctx):
    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send(
        embed=Embed(
            title="📦 TAMBAH PRODUK BARU",
            description="Ikuti langkah-langkah berikut:",
            color=Color.blue()
        )
    )

    try:
        # NAMA
        await ctx.send("**[1/4]** 📝 Masukkan **nama produk**:")
        msg  = await bot.wait_for("message", check=chk, timeout=60)
        nama = msg.content.strip()
        if not nama:
            await ctx.send("❌ Nama tidak boleh kosong!")
            return

        # HARGA
        await ctx.send(f"**[2/4]** 💰 Masukkan **harga** `{nama}` (angka saja, contoh: `25000`):")
        msg = await bot.wait_for("message", check=chk, timeout=60)
        try:
            harga = int(msg.content.strip())
            if harga <= 0:
                raise ValueError
        except ValueError:
            await ctx.send("❌ Harga harus berupa angka positif!")
            return

        # STOK
        await ctx.send(f"**[3/4]** 📊 Masukkan **stok** `{nama}`:")
        msg = await bot.wait_for("message", check=chk, timeout=60)
        try:
            stok = int(msg.content.strip())
            if stok < 0:
                raise ValueError
        except ValueError:
            await ctx.send("❌ Stok harus berupa angka!")
            return

        # FILE
        await ctx.send(f"**[4/4]** 📎 Upload **file `.rbxm`** untuk `{nama}`:")
        msg = await bot.wait_for("message", check=chk, timeout=120)
        if not msg.attachments:
            await ctx.send("❌ Kamu harus upload file!")
            return

        att = msg.attachments[0]
        if not att.filename.lower().endswith(".rbxm"):
            await ctx.send("❌ File harus berformat **`.rbxm`**!")
            return

        # Simpan ke storage
        storage_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
        if not storage_id:
            await ctx.send("❌ Channel `produk-storage` belum diset!")
            return

        storage_ch = ctx.guild.get_channel(int(storage_id))
        if not storage_ch:
            await ctx.send("❌ Channel `produk-storage` tidak ditemukan!")
            return

        file_bytes = await att.read()

        st_emb = Embed(
            title=f"📁 STORAGE — {nama}",
            color=Color.blue()
        )
        st_emb.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
        st_emb.add_field(name="📊 Stok",  value=str(stok),            inline=True)
        st_emb.set_footer(text=f"TALANG SHOP • Auto-saved")

        st_msg = await storage_ch.send(
            embed=st_emb,
            file=discord.File(fp=io.BytesIO(file_bytes), filename=att.filename)
        )

        # Simpan ke DB
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO produk (nama, harga, stok, file_message_id) VALUES (?,?,?,?)",
                (nama, harga, stok, st_msg.id)
            )
            await db.commit()

        done_emb = Embed(
            title="✅ PRODUK BERHASIL DITAMBAHKAN!",
            color=Color.green(),
            timestamp=datetime.now()
        )
        done_emb.add_field(name="📦 Nama",  value=nama,                 inline=True)
        done_emb.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
        done_emb.add_field(name="📊 Stok",  value=str(stok),            inline=True)
        done_emb.add_field(name="📎 File",  value=att.filename,         inline=True)
        await ctx.send(embed=done_emb)

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout! Jalankan `!addproduk` ulang.")

# ============================================================
# COMMANDS: LIST PRODUK
# ============================================================
@bot.command(name="listproduk")
@commands.has_permissions(administrator=True)
async def cmd_listproduk(ctx):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, nama, harga, stok, active FROM produk ORDER BY id"
        ) as cur:
            products = await cur.fetchall()

    if not products:
        await ctx.send("❌ Belum ada produk!")
        return

    emb = Embed(
        title="📦 DAFTAR SEMUA PRODUK",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    for p in products:
        pid, nama, harga, stok, active = p
        status = "✅ Aktif" if active else "❌ Nonaktif"
        emb.add_field(
            name=f"#{pid} — {nama}",
            value=f"💰 {format_rupiah(harga)} | 📊 Stok: {stok} | {status}",
            inline=False
        )
    emb.set_footer(text="TALANG SHOP")
    await ctx.send(embed=emb)

# ============================================================
# COMMANDS: EDIT PRODUK
# ============================================================
@bot.command(name="editproduk")
@commands.has_permissions(administrator=True)
async def cmd_editproduk(ctx):
    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, nama, harga, stok FROM produk WHERE active=1 ORDER BY id"
        ) as cur:
            products = await cur.fetchall()

    if not products:
        await ctx.send("❌ Belum ada produk aktif!")
        return

    list_str = "\n".join(
        [f"**#{p[0]}** — {p[1]} | {format_rupiah(p[2])} | Stok: {p[3]}"
         for p in products]
    )
    await ctx.send(
        embed=Embed(
            title="✏️ EDIT PRODUK",
            description=f"{list_str}\n\n📝 Masukkan **ID produk** yang ingin diedit:",
            color=Color.blue()
        )
    )

    try:
        msg    = await bot.wait_for("message", check=chk, timeout=60)
        prod_id = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT nama, harga, stok FROM produk WHERE id=? AND active=1",
                (prod_id,)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send("❌ Produk tidak ditemukan!")
            return

        nama_now, harga_now, stok_now = row

        await ctx.send(
            embed=Embed(
                title=f"✏️ Edit Produk #{prod_id} — {nama_now}",
                description=(
                    f"1️⃣ Nama  (sekarang: **{nama_now}**)\n"
                    f"2️⃣ Harga (sekarang: **{format_rupiah(harga_now)}**)\n"
                    f"3️⃣ Stok  (sekarang: **{stok_now}**)\n"
                    f"4️⃣ File .rbxm\n\n"
                    f"Ketik angka **(1/2/3/4)**:"
                ),
                color=Color.blue()
            )
        )

        msg    = await bot.wait_for("message", check=chk, timeout=60)
        choice = msg.content.strip()

        async with aiosqlite.connect(DB_FILE) as db:
            if choice == "1":
                await ctx.send("📝 Masukkan **nama baru**:")
                msg = await bot.wait_for("message", check=chk, timeout=60)
                await db.execute(
                    "UPDATE produk SET nama=? WHERE id=?",
                    (msg.content.strip(), prod_id)
                )
                await ctx.send(f"✅ Nama diubah → **{msg.content.strip()}**")

            elif choice == "2":
                await ctx.send("💰 Masukkan **harga baru** (angka saja):")
                msg = await bot.wait_for("message", check=chk, timeout=60)
                new_h = int(msg.content.strip())
                await db.execute("UPDATE produk SET harga=? WHERE id=?", (new_h, prod_id))
                await ctx.send(f"✅ Harga diubah → **{format_rupiah(new_h)}**")

            elif choice == "3":
                await ctx.send("📊 Masukkan **stok baru**:")
                msg = await bot.wait_for("message", check=chk, timeout=60)
                new_s = int(msg.content.strip())
                await db.execute("UPDATE produk SET stok=? WHERE id=?", (new_s, prod_id))
                await ctx.send(f"✅ Stok diubah → **{new_s}**")

            elif choice == "4":
                await ctx.send("📎 Upload **file `.rbxm` baru**:")
                msg = await bot.wait_for("message", check=chk, timeout=120)
                if not msg.attachments or not msg.attachments[0].filename.lower().endswith(".rbxm"):
                    await ctx.send("❌ Upload file `.rbxm` yang valid!")
                    return

                storage_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
                storage_ch = ctx.guild.get_channel(int(storage_id)) if storage_id else None
                if not storage_ch:
                    await ctx.send("❌ Channel `produk-storage` tidak ditemukan!")
                    return

                att        = msg.attachments[0]
                file_bytes = await att.read()
                st_msg     = await storage_ch.send(
                    content=f"📁 UPDATE — Produk #{prod_id}",
                    file=discord.File(fp=io.BytesIO(file_bytes), filename=att.filename)
                )
                await db.execute(
                    "UPDATE produk SET file_message_id=? WHERE id=?",
                    (st_msg.id, prod_id)
                )
                await ctx.send(f"✅ File diupdate → **{att.filename}**")

            else:
                await ctx.send("❌ Pilihan tidak valid!")
                return

            await db.commit()

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka yang valid!")

# ============================================================
# COMMANDS: HAPUS PRODUK
# ============================================================
@bot.command(name="delproduk")
@commands.has_permissions(administrator=True)
async def cmd_delproduk(ctx):
    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, nama, harga FROM produk WHERE active=1 ORDER BY id"
        ) as cur:
            products = await cur.fetchall()

    if not products:
        await ctx.send("❌ Tidak ada produk aktif!")
        return

    list_str = "\n".join(
        [f"**#{p[0]}** — {p[1]} | {format_rupiah(p[2])}" for p in products]
    )
    await ctx.send(
        embed=Embed(
            title="🗑️ HAPUS PRODUK",
            description=f"{list_str}\n\n📝 Masukkan **ID produk** yang ingin dihapus:",
            color=Color.red()
        )
    )

    try:
        msg     = await bot.wait_for("message", check=chk, timeout=60)
        prod_id = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT nama FROM produk WHERE id=? AND active=1", (prod_id,)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                await ctx.send("❌ Produk tidak ditemukan!")
                return

            await db.execute(
                "UPDATE produk SET active=0 WHERE id=?", (prod_id,)
            )
            await db.commit()

        await ctx.send(
            embed=Embed(
                description=f"✅ Produk **{row[0]}** (#{prod_id}) berhasil dihapus!",
                color=Color.green()
            )
        )

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka ID yang valid!")

# ============================================================
# COMMANDS: UPDATE STOK
# ============================================================
@bot.command(name="stok")
@commands.has_permissions(administrator=True)
async def cmd_stok(ctx):
    def chk(m):
        return m.author == ctx.author and m.channel == ctx.channel

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id, nama, stok FROM produk WHERE active=1 ORDER BY id"
        ) as cur:
            products = await cur.fetchall()

    if not products:
        await ctx.send("❌ Tidak ada produk!")
        return

    list_str = "\n".join(
        [f"**#{p[0]}** — {p[1]} | Stok: **{p[2]}**" for p in products]
    )
    await ctx.send(
        embed=Embed(
            title="📊 UPDATE STOK",
            description=f"{list_str}\n\n📝 Masukkan **ID produk**:",
            color=Color.blue()
        )
    )

    try:
        msg     = await bot.wait_for("message", check=chk, timeout=60)
        prod_id = int(msg.content.strip())

        await ctx.send("📊 Masukkan **stok baru**:")
        msg      = await bot.wait_for("message", check=chk, timeout=60)
        new_stok = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT nama FROM produk WHERE id=? AND active=1", (prod_id,)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                await ctx.send("❌ Produk tidak ditemukan!")
                return

            await db.execute(
                "UPDATE produk SET stok=? WHERE id=?", (new_stok, prod_id)
            )
            await db.commit()

        await ctx.send(
            embed=Embed(
                description=f"✅ Stok **{row[0]}** diupdate → **{new_stok}**",
                color=Color.green()
            )
        )

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka yang valid!")

# ============================================================
# COMMANDS: HELP
# ============================================================
@bot.command(name="help")
async def cmd_help(ctx):
    if not is_owner(ctx.author):
        return

    emb = Embed(
        title="📖 TALANG SHOP — COMMAND LIST",
        description="Daftar semua command yang tersedia untuk **OWNER**:",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    emb.add_field(
        name="⚙️ Setup Awal",
        value=(
            "`!setchannel` — Set semua channel & category\n"
            "`!setqris`    — Upload / update gambar QRIS\n"
            "`!setup`      — Kirim embed open tiket\n"
        ),
        inline=False
    )
    emb.add_field(
        name="📦 Kelola Produk",
        value=(
            "`!addproduk`  — Tambah produk baru\n"
            "`!listproduk` — Lihat semua produk\n"
            "`!editproduk` — Edit produk\n"
            "`!delproduk`  — Hapus produk\n"
            "`!stok`       — Update stok produk\n"
        ),
        inline=False
    )
    emb.set_footer(text="TALANG SHOP • Hanya OWNER yang bisa menggunakan command ini")
    await ctx.send(embed=emb, ephemeral=True)

# ============================================================
# EVENTS
# ============================================================
@bot.event
async def on_ready():
    await init_db()
    # Register persistent views
    bot.add_view(OpenTiketView())
    print("=" * 55)
    print(f"  🤖  {config['BOT_NAME']} is ONLINE!")
    print(f"  📌  Logged in as : {bot.user}")
    print(f"  📌  Bot ID       : {bot.user.id}")
    print(f"  📌  Prefix       : {config['PREFIX']}")
    print(f"  📌  DB File      : {DB_FILE}")
    print("=" * 55)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Kamu tidak punya izin untuk command ini!")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("❌ Akses ditolak!")
    else:
        await ctx.send(f"❌ Terjadi error: `{error}`")
        raise error

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        print("❌ TOKEN tidak ditemukan!")
        print("   Pastikan file .env ada dan berisi TOKEN=xxx")
        print("   Atau set Environment Variable TOKEN di Railway.")
    else:
        print(f"🚀 Starting {config['BOT_NAME']}...")
        bot.run(TOKEN)
