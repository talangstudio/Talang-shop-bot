import discord
from discord.ext import commands
from discord import ui, ButtonStyle, Interaction, Embed, Color, PermissionOverwrite
import aiosqlite
import json
import os
import asyncio
from datetime import datetime

# ============================================================
# LOAD CONFIG
# ============================================================
CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

config = load_config()

# ============================================================
# BOT SETUP
# ============================================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config["PREFIX"], intents=intents, help_command=None)

DB_FILE = "database.db"

# ============================================================
# DATABASE SETUP
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
        await db.execute("INSERT OR IGNORE INTO tiket_counter (id, counter) VALUES (1, 0)")
        await db.commit()

async def get_next_tiket_number():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE tiket_counter SET counter = counter + 1 WHERE id = 1")
        await db.commit()
        async with db.execute("SELECT counter FROM tiket_counter WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return row[0]

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def is_owner(member: discord.Member) -> bool:
    role_name = config["OWNER_ROLE_NAME"]
    return any(role.name == role_name for role in member.roles) or member.guild_permissions.administrator

def format_rupiah(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def log_progres(guild, tiket_number, user, kategori, status, detail=""):
    channel_id = config.get("CHANNEL_PROGRES_TIKET_ID")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
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
        title=f"📋 TIKET #{tiket_number:04d}",
        color=color_map.get(status, Color.greyple()),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=f"{user.mention}", inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    embed.add_field(name="📊 Status", value=f"{emoji_map.get(status, '⚪')} {status}", inline=True)
    if detail:
        embed.add_field(name="📝 Detail", value=detail, inline=False)
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")

    await channel.send(embed=embed)

async def send_notifikasi(guild, user, kategori, detail=""):
    channel_id = config.get("CHANNEL_NOTIFIKASI_ID")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return

    embed = Embed(
        title="🎉 TRANSAKSI BERHASIL!",
        color=Color.gold(),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=f"{user.mention}", inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    if detail:
        embed.add_field(name="📝 Detail", value=detail, inline=False)
    embed.add_field(name="⭐", value="Terima kasih sudah menggunakan layanan **TALANG SHOP**!", inline=False)
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")

    await channel.send(content="@everyone", embed=embed)

async def send_review_to_channel(guild, user, kategori, rating, review_text):
    channel_id = config.get("CHANNEL_REVIEW_ID")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not channel:
        return

    stars = "⭐" * rating + "☆" * (5 - rating)

    embed = Embed(
        title="📝 REVIEW BARU",
        color=Color.gold(),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Member", value=f"{user.mention}", inline=True)
    embed.add_field(name="📂 Kategori", value=kategori, inline=True)
    embed.add_field(name="⭐ Rating", value=f"{stars} ({rating}/5)", inline=False)
    embed.add_field(name="💬 Review", value=f'"{review_text}"', inline=False)
    embed.set_footer(text=f"TALANG SHOP • {get_timestamp()}")

    await channel.send(content="@everyone", embed=embed)

# ============================================================
# VIEWS - OPEN TIKET
# ============================================================
class OpenTiketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🎫 Open Tiket", style=ButtonStyle.blurple, custom_id="open_tiket_main")
    async def open_tiket(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(
            embed=Embed(
                title="📂 Pilih Kategori Tiket",
                description="Silakan pilih layanan yang kamu butuhkan:",
                color=Color.blue()
            ),
            view=KategoriTiketView(),
            ephemeral=True
        )

class KategoriTiketView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="🛒 Beli Produk", style=ButtonStyle.green, custom_id="kat_beli", row=0)
    async def beli_produk(self, interaction: Interaction, button: ui.Button):
        await self.create_tiket(interaction, "Beli Produk")

    @ui.button(label="🔧 Fix System", style=ButtonStyle.blurple, custom_id="kat_fix", row=0)
    async def fix_system(self, interaction: Interaction, button: ui.Button):
        await self.create_tiket(interaction, "Fix System")

    @ui.button(label="🎨 Custom System", style=ButtonStyle.blurple, custom_id="kat_custom", row=1)
    async def custom_system(self, interaction: Interaction, button: ui.Button):
        await self.create_tiket(interaction, "Custom System")

    @ui.button(label="🗺️ Jasa Buat Maps", style=ButtonStyle.blurple, custom_id="kat_maps", row=1)
    async def jasa_maps(self, interaction: Interaction, button: ui.Button):
        await self.create_tiket(interaction, "Jasa Buat Maps")

    @ui.button(label="💬 Konsultasi", style=ButtonStyle.grey, custom_id="kat_konsul", row=2)
    async def konsultasi(self, interaction: Interaction, button: ui.Button):
        await self.create_tiket(interaction, "Konsultasi dengan Staff")

    async def create_tiket(self, interaction: Interaction, kategori: str):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user
        category_id = config.get("CATEGORY_TIKET_ID")

        if not category_id:
            await interaction.followup.send("❌ Category tiket belum diset! Minta OWNER jalankan `!setchannel`", ephemeral=True)
            return

        category = guild.get_channel(int(category_id))
        if not category:
            await interaction.followup.send("❌ Category tiket tidak ditemukan!", ephemeral=True)
            return

        # Cek apakah user sudah punya tiket aktif
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE user_id = ? AND status != 'CLOSED'", (user.id,)
            ) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    await interaction.followup.send("❌ Kamu sudah punya tiket aktif! Selesaikan dulu tiket sebelumnya.", ephemeral=True)
                    return

        tiket_number = await get_next_tiket_number()
        channel_name = f"tiket-{user.name}-{tiket_number:04d}"

        # Permission
        overwrites = {
            guild.default_role: PermissionOverwrite(view_channel=False),
            user: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True
            ),
            guild.me: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                attach_files=True
            )
        }

        # Add OWNER role permission
        owner_role = discord.utils.get(guild.roles, name=config["OWNER_ROLE_NAME"])
        if owner_role:
            overwrites[owner_role] = PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                attach_files=True,
                read_message_history=True
            )

        tiket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )

        # Save to DB
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """INSERT INTO tiket (tiket_number, user_id, username, kategori, channel_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'OPEN', ?)""",
                (tiket_number, user.id, user.name, kategori, tiket_channel.id, get_timestamp())
            )
            await db.commit()

        # Log progres
        await log_progres(guild, tiket_number, user, kategori, "OPEN")

        # Welcome embed
        welcome_embed = Embed(
            title=f"🎫 TIKET #{tiket_number:04d}",
            description=f"Selamat datang di tiket kamu, {user.mention}!",
            color=Color.blue(),
            timestamp=datetime.now()
        )
        welcome_embed.add_field(name="📂 Kategori", value=kategori, inline=True)
        welcome_embed.add_field(name="👤 Member", value=user.mention, inline=True)
        welcome_embed.add_field(name="📊 Status", value="🔵 OPEN", inline=True)
        welcome_embed.set_footer(text=f"TALANG SHOP • Tiket #{tiket_number:04d}")

        await tiket_channel.send(embed=welcome_embed)

        if kategori == "Beli Produk":
            await self.show_products_in_ticket(tiket_channel, user, tiket_number)
        else:
            service_embed = Embed(
                title=f"📂 {kategori}",
                description="Silakan jelaskan kebutuhan kamu di sini.\nStaff **OWNER** akan segera merespon.",
                color=Color.blue()
            )
            await tiket_channel.send(embed=service_embed)
            await tiket_channel.send(view=ServiceControlView(tiket_number))

        await interaction.followup.send(
            f"✅ Tiket berhasil dibuat! Silakan cek {tiket_channel.mention}",
            ephemeral=True
        )

    async def show_products_in_ticket(self, channel, user, tiket_number):
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id, nama, harga, stok FROM produk WHERE active = 1"
            ) as cursor:
                products = await cursor.fetchall()

        if not products:
            embed = Embed(
                title="🛒 DAFTAR PRODUK",
                description="❌ Belum ada produk yang tersedia saat ini.",
                color=Color.red()
            )
            await channel.send(embed=embed)
            await channel.send(view=ServiceControlView(tiket_number))
            return

        header_embed = Embed(
            title="🛒 DAFTAR PRODUK - TALANG SHOP",
            description="Pilih produk yang ingin kamu beli dengan menekan tombol **Beli** di bawah setiap produk.",
            color=Color.gold()
        )
        header_embed.set_footer(text="TALANG SHOP • Katalog Produk")
        await channel.send(embed=header_embed)

        for product in products:
            prod_id, nama, harga, stok = product

            stok_status = f"📊 Stok: **{stok}**" if stok > 0 else "📊 Stok: **HABIS** ❌"

            prod_embed = Embed(
                title=f"📦 {nama}",
                color=Color.green() if stok > 0 else Color.red()
            )
            prod_embed.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
            prod_embed.add_field(name="📊 Stok", value=str(stok) if stok > 0 else "HABIS", inline=True)

            view = ProductBuyView(prod_id, nama, harga, stok, tiket_number) if stok > 0 else None
            await channel.send(embed=prod_embed, view=view)

        await channel.send("─" * 40)
        await channel.send(view=ServiceControlView(tiket_number))


# ============================================================
# VIEWS - PRODUCT BUY
# ============================================================
class ProductBuyView(ui.View):
    def __init__(self, prod_id, nama, harga, stok, tiket_number):
        super().__init__(timeout=None)
        self.prod_id = prod_id
        self.nama = nama
        self.harga = harga
        self.stok = stok
        self.tiket_number = tiket_number

        buy_button = ui.Button(
            label=f"🛒 Beli {nama}",
            style=ButtonStyle.green,
            custom_id=f"buy_product_{prod_id}_{tiket_number}"
        )
        buy_button.callback = self.buy_callback
        self.add_item(buy_button)

    async def buy_callback(self, interaction: Interaction):
        # Cek stok terbaru
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT stok FROM produk WHERE id = ?", (self.prod_id,)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] <= 0:
                    await interaction.response.send_message("❌ Maaf, produk ini sudah habis!", ephemeral=True)
                    return

        await interaction.response.defer()

        # Detail pesanan
        order_embed = Embed(
            title="🧾 DETAIL PESANAN",
            color=Color.gold(),
            timestamp=datetime.now()
        )
        order_embed.add_field(name="📦 Produk", value=self.nama, inline=True)
        order_embed.add_field(name="💰 Harga", value=format_rupiah(self.harga), inline=True)
        order_embed.add_field(
            name="💳 Pembayaran",
            value="Silakan bayar via **QRIS** di bawah ini lalu kirim **bukti pembayaran** di channel ini.",
            inline=False
        )
        order_embed.set_footer(text=f"TALANG SHOP • Tiket #{self.tiket_number:04d}")

        await interaction.channel.send(embed=order_embed)

        # QRIS Image
        qris_url = config.get("QRIS_IMAGE_URL")
        if qris_url:
            qris_embed = Embed(title="📱 SCAN QRIS", color=Color.blue())
            qris_embed.set_image(url=qris_url)
            await interaction.channel.send(embed=qris_embed)

        await interaction.channel.send(
            "📸 **Kirim bukti pembayaran kamu di channel ini.**\n"
            "⏳ Menunggu bukti pembayaran..."
        )

        # Save transaksi
        async with aiosqlite.connect(DB_FILE) as db:
            # Get tiket ID
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
            ) as cursor:
                tiket_row = await cursor.fetchone()
                tiket_id = tiket_row[0] if tiket_row else None

            await db.execute(
                """INSERT INTO transaksi (tiket_id, user_id, produk_id, produk_nama, total_harga, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'MENUNGGU PEMBAYARAN', ?)""",
                (tiket_id, interaction.user.id, self.prod_id, self.nama, self.harga, get_timestamp())
            )

            # Update tiket
            await db.execute(
                "UPDATE tiket SET produk_id = ?, status = 'MENUNGGU PEMBAYARAN' WHERE tiket_number = ?",
                (self.prod_id, self.tiket_number)
            )
            await db.commit()

        # Log progres
        await log_progres(
            interaction.guild, self.tiket_number, interaction.user,
            "Beli Produk", "MENUNGGU PEMBAYARAN",
            f"Produk: {self.nama} | Total: {format_rupiah(self.harga)}"
        )

        # Aktifkan listener bukti bayar
        await self.wait_for_payment_proof(interaction)

    async def wait_for_payment_proof(self, interaction: Interaction):
        channel = interaction.channel
        user = interaction.user

        def check(m):
            return (
                m.channel.id == channel.id
                and m.author.id == user.id
                and len(m.attachments) > 0
            )

        try:
            msg = await bot.wait_for("message", check=check, timeout=1800)  # 30 menit

            bukti_embed = Embed(
                title="📸 BUKTI PEMBAYARAN DITERIMA",
                color=Color.orange(),
                timestamp=datetime.now()
            )
            bukti_embed.add_field(name="👤 Member", value=user.mention, inline=True)
            bukti_embed.add_field(name="📦 Produk", value=self.nama, inline=True)
            bukti_embed.add_field(name="💰 Total", value=format_rupiah(self.harga), inline=True)
            if msg.attachments:
                bukti_embed.set_image(url=msg.attachments[0].url)
            bukti_embed.set_footer(text=f"TALANG SHOP • Tiket #{self.tiket_number:04d}")

            # Update transaksi
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute(
                    "SELECT id FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
                ) as cursor:
                    tiket_row = await cursor.fetchone()
                    tiket_id = tiket_row[0] if tiket_row else None

                await db.execute(
                    "UPDATE transaksi SET status = 'BUKTI DIKIRIM', bukti_message_id = ? WHERE tiket_id = ?",
                    (msg.id, tiket_id)
                )
                await db.execute(
                    "UPDATE tiket SET status = 'BUKTI DIKIRIM' WHERE tiket_number = ?",
                    (self.tiket_number,)
                )
                await db.commit()

            await log_progres(
                interaction.guild, self.tiket_number, user,
                "Beli Produk", "BUKTI DIKIRIM",
                f"Produk: {self.nama}"
            )

            await channel.send(
                embed=bukti_embed,
                view=PaymentConfirmView(self.prod_id, self.nama, self.harga, self.tiket_number, user)
            )

        except asyncio.TimeoutError:
            await channel.send(
                f"⏰ {user.mention} Waktu pembayaran habis (30 menit). "
                f"Silakan buat tiket baru jika masih ingin membeli."
            )


# ============================================================
# VIEWS - PAYMENT CONFIRM (OWNER ONLY)
# ============================================================
class PaymentConfirmView(ui.View):
    def __init__(self, prod_id, nama, harga, tiket_number, buyer):
        super().__init__(timeout=None)
        self.prod_id = prod_id
        self.nama = nama
        self.harga = harga
        self.tiket_number = tiket_number
        self.buyer = buyer

    @ui.button(label="✅ Konfirmasi Bayar", style=ButtonStyle.green, custom_id="confirm_pay")
    async def confirm_payment(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ Hanya **OWNER** yang bisa konfirmasi pembayaran!", ephemeral=True)
            return

        await interaction.response.defer()

        # Update DB
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
            ) as cursor:
                tiket_row = await cursor.fetchone()
                tiket_id = tiket_row[0] if tiket_row else None

            await db.execute(
                "UPDATE transaksi SET status = 'LUNAS', confirmed_at = ? WHERE tiket_id = ?",
                (get_timestamp(), tiket_id)
            )
            await db.execute(
                "UPDATE tiket SET status = 'LUNAS' WHERE tiket_number = ?",
                (self.tiket_number,)
            )

            # Kurangi stok
            await db.execute(
                "UPDATE produk SET stok = stok - 1 WHERE id = ? AND stok > 0",
                (self.prod_id,)
            )
            await db.commit()

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            "Beli Produk", "LUNAS",
            f"Produk: {self.nama} | Dikonfirmasi oleh: {interaction.user.mention}"
        )

        # Konfirmasi embed
        confirm_embed = Embed(
            title="✅ PEMBAYARAN DIKONFIRMASI!",
            description=f"Pembayaran untuk **{self.nama}** telah dikonfirmasi oleh {interaction.user.mention}",
            color=Color.green(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=confirm_embed)

        # Kirim produk otomatis
        await self.send_product(interaction)

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    @ui.button(label="❌ Tolak Pembayaran", style=ButtonStyle.red, custom_id="reject_pay")
    async def reject_payment(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ Hanya **OWNER** yang bisa menolak pembayaran!", ephemeral=True)
            return

        # Modal untuk alasan penolakan
        modal = RejectReasonModal(self.tiket_number, self.nama, self.buyer)
        await interaction.response.send_modal(modal)

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

    async def send_product(self, interaction: Interaction):
        # Cari file produk di #produk-storage
        storage_channel_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
        if not storage_channel_id:
            await interaction.channel.send("❌ Channel produk-storage belum diset!")
            return

        storage_channel = interaction.guild.get_channel(int(storage_channel_id))
        if not storage_channel:
            await interaction.channel.send("❌ Channel produk-storage tidak ditemukan!")
            return

        # Cari message dengan file produk
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT file_message_id FROM produk WHERE id = ?", (self.prod_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row or not row[0]:
                    await interaction.channel.send("❌ File produk tidak ditemukan di database!")
                    return
                file_message_id = row[0]

        try:
            file_message = await storage_channel.fetch_message(file_message_id)
            if file_message.attachments:
                attachment = file_message.attachments[0]
                file_data = await attachment.read()

                product_embed = Embed(
                    title="📦 PRODUK DIKIRIM!",
                    description=f"Berikut file produk **{self.nama}** kamu:",
                    color=Color.green(),
                    timestamp=datetime.now()
                )
                product_embed.add_field(name="📎 File", value=attachment.filename, inline=True)
                product_embed.add_field(name="💰 Total Bayar", value=format_rupiah(self.harga), inline=True)
                product_embed.set_footer(text=f"TALANG SHOP • Tiket #{self.tiket_number:04d}")

                await interaction.channel.send(embed=product_embed)
                await interaction.channel.send(
                    file=discord.File(fp=__import__('io').BytesIO(file_data), filename=attachment.filename)
                )

                # Update status
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute(
                        "UPDATE tiket SET status = 'PRODUK TERKIRIM' WHERE tiket_number = ?",
                        (self.tiket_number,)
                    )
                    await db.execute(
                        "UPDATE transaksi SET status = 'PRODUK TERKIRIM' WHERE tiket_id = (SELECT id FROM tiket WHERE tiket_number = ?)",
                        (self.tiket_number,)
                    )
                    await db.commit()

                await log_progres(
                    interaction.guild, self.tiket_number, self.buyer,
                    "Beli Produk", "PRODUK TERKIRIM",
                    f"Produk: {self.nama} | File: {attachment.filename}"
                )

                # Kirim notifikasi
                await send_notifikasi(
                    interaction.guild, self.buyer, "Beli Produk",
                    f"Produk: **{self.nama}** | Total: **{format_rupiah(self.harga)}**"
                )

                # Minta rating
                await interaction.channel.send(
                    f"\n{self.buyer.mention} Terima kasih sudah berbelanja! 🎉\n"
                    f"Silakan berikan **rating & review** untuk layanan kami:",
                    view=RatingView(self.tiket_number, "Beli Produk", self.buyer)
                )

            else:
                await interaction.channel.send("❌ File tidak ditemukan di message storage!")

        except discord.NotFound:
            await interaction.channel.send("❌ Message produk di storage tidak ditemukan! Mungkin sudah dihapus.")
        except Exception as e:
            await interaction.channel.send(f"❌ Error saat mengirim produk: {str(e)}")


# ============================================================
# MODAL - REJECT REASON
# ============================================================
class RejectReasonModal(ui.Modal, title="Alasan Penolakan"):
    reason = ui.TextInput(
        label="Alasan",
        placeholder="Masukkan alasan penolakan pembayaran...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, tiket_number, nama, buyer):
        super().__init__()
        self.tiket_number = tiket_number
        self.nama = nama
        self.buyer = buyer

    async def on_submit(self, interaction: Interaction):
        reject_embed = Embed(
            title="❌ PEMBAYARAN DITOLAK",
            color=Color.red(),
            timestamp=datetime.now()
        )
        reject_embed.add_field(name="📦 Produk", value=self.nama, inline=True)
        reject_embed.add_field(name="❌ Ditolak oleh", value=interaction.user.mention, inline=True)
        reject_embed.add_field(name="📝 Alasan", value=self.reason.value, inline=False)
        reject_embed.add_field(
            name="ℹ️ Info",
            value="Silakan lakukan pembayaran ulang atau hubungi staff.",
            inline=False
        )

        await interaction.response.send_message(embed=reject_embed)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE transaksi SET status = 'DITOLAK' WHERE tiket_id = (SELECT id FROM tiket WHERE tiket_number = ?)",
                (self.tiket_number,)
            )
            await db.execute(
                "UPDATE tiket SET status = 'DITOLAK' WHERE tiket_number = ?",
                (self.tiket_number,)
            )
            await db.commit()

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            "Beli Produk", "DITOLAK",
            f"Alasan: {self.reason.value}"
        )


# ============================================================
# VIEWS - RATING
# ============================================================
class RatingView(ui.View):
    def __init__(self, tiket_number, kategori, buyer):
        super().__init__(timeout=None)
        self.tiket_number = tiket_number
        self.kategori = kategori
        self.buyer = buyer

        for i in range(1, 6):
            btn = ui.Button(
                label=f"{'⭐' * i}",
                style=ButtonStyle.grey,
                custom_id=f"rating_{tiket_number}_{i}",
                row=0
            )
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, rating):
        async def callback(interaction: Interaction):
            if interaction.user.id != self.buyer.id:
                await interaction.response.send_message("❌ Hanya pembuat tiket yang bisa memberikan rating!", ephemeral=True)
                return
            modal = ReviewModal(self.tiket_number, self.kategori, self.buyer, rating)
            await interaction.response.send_modal(modal)

            # Disable all buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)

        return callback


class ReviewModal(ui.Modal, title="Tulis Review"):
    review_text = ui.TextInput(
        label="Review",
        placeholder="Tulis review kamu tentang layanan kami...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, tiket_number, kategori, buyer, rating):
        super().__init__()
        self.tiket_number = tiket_number
        self.kategori = kategori
        self.buyer = buyer
        self.rating = rating

    async def on_submit(self, interaction: Interaction):
        # Save review
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT id FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
            ) as cursor:
                tiket_row = await cursor.fetchone()
                tiket_id = tiket_row[0] if tiket_row else None

            await db.execute(
                """INSERT INTO review (user_id, username, tiket_id, kategori, rating, review_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (self.buyer.id, self.buyer.name, tiket_id, self.kategori, self.rating, self.review_text.value, get_timestamp())
            )
            await db.commit()

        stars = "⭐" * self.rating + "☆" * (5 - self.rating)

        review_embed = Embed(
            title="✅ Review Diterima!",
            color=Color.gold()
        )
        review_embed.add_field(name="⭐ Rating", value=f"{stars} ({self.rating}/5)", inline=False)
        review_embed.add_field(name="💬 Review", value=f'"{self.review_text.value}"', inline=False)

        await interaction.response.send_message(embed=review_embed)

        # Kirim ke channel review
        await send_review_to_channel(
            interaction.guild, self.buyer, self.kategori, self.rating, self.review_text.value
        )

        await log_progres(
            interaction.guild, self.tiket_number, self.buyer,
            self.kategori, "SELESAI",
            f"Rating: {self.rating}/5"
        )


# ============================================================
# VIEWS - SERVICE CONTROL (Close + Selesai)
# ============================================================
class ServiceControlView(ui.View):
    def __init__(self, tiket_number):
        super().__init__(timeout=None)
        self.tiket_number = tiket_number

    @ui.button(label="✅ Selesai", style=ButtonStyle.green, custom_id="service_done")
    async def service_done(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ Hanya **OWNER** yang bisa menyelesaikan tiket!", ephemeral=True)
            return

        await interaction.response.defer()

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT user_id, kategori FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await interaction.followup.send("❌ Tiket tidak ditemukan!")
                    return
                user_id, kategori = row

            await db.execute(
                "UPDATE tiket SET status = 'SELESAI' WHERE tiket_number = ?",
                (self.tiket_number,)
            )
            await db.commit()

        buyer = interaction.guild.get_member(user_id)

        done_embed = Embed(
            title="✅ LAYANAN SELESAI!",
            description=f"Tiket #{self.tiket_number:04d} telah diselesaikan oleh {interaction.user.mention}",
            color=Color.green(),
            timestamp=datetime.now()
        )
        await interaction.channel.send(embed=done_embed)

        if buyer:
            await send_notifikasi(
                interaction.guild, buyer, kategori,
                f"Layanan **{kategori}** telah selesai!"
            )

            await interaction.channel.send(
                f"\n{buyer.mention} Terima kasih! 🎉\nSilakan berikan **rating & review** untuk layanan kami:",
                view=RatingView(self.tiket_number, kategori, buyer)
            )

            await log_progres(interaction.guild, self.tiket_number, buyer, kategori, "SELESAI")

        # Disable button
        for item in self.children:
            if item.custom_id == "service_done":
                item.disabled = True
        await interaction.message.edit(view=self)

    @ui.button(label="🔒 Close Tiket", style=ButtonStyle.red, custom_id="close_tiket")
    async def close_tiket(self, interaction: Interaction, button: ui.Button):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ Hanya **OWNER** yang bisa menutup tiket!", ephemeral=True)
            return

        await interaction.response.defer()

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute(
                "SELECT user_id, kategori FROM tiket WHERE tiket_number = ?", (self.tiket_number,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_id, kategori = row
                    buyer = interaction.guild.get_member(user_id)
                    if buyer:
                        await log_progres(interaction.guild, self.tiket_number, buyer, kategori, "CLOSED")

            await db.execute(
                "UPDATE tiket SET status = 'CLOSED', closed_at = ? WHERE tiket_number = ?",
                (get_timestamp(), self.tiket_number)
            )
            await db.commit()

        close_embed = Embed(
            title="🔒 TIKET DITUTUP",
            description="Tiket ini akan dihapus dalam **5 detik**...",
            color=Color.dark_grey()
        )
        await interaction.channel.send(embed=close_embed)

        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Tiket #{self.tiket_number:04d} ditutup")


# ============================================================
# COMMANDS - SETUP
# ============================================================
@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    channel_id = config.get("CHANNEL_OPEN_TIKET_ID")
    if not channel_id:
        await ctx.send("❌ Channel open-tiket belum diset! Jalankan `!setchannel` dulu.")
        return

    channel = ctx.guild.get_channel(int(channel_id))
    if not channel:
        await ctx.send("❌ Channel open-tiket tidak ditemukan!")
        return

    embed = Embed(
        title="🎫 TALANG SHOP - TICKET SYSTEM",
        description=(
            "Selamat datang di **TALANG SHOP**! 🛒\n\n"
            "Klik tombol di bawah untuk membuka tiket.\n"
            "Pilih layanan yang kamu butuhkan:\n\n"
            "🛒 **Beli Produk** - Beli produk .rbxm\n"
            "🔧 **Fix System** - Perbaikan system\n"
            "🎨 **Custom System** - Request custom system\n"
            "🗺️ **Jasa Buat Maps** - Pembuatan maps\n"
            "💬 **Konsultasi** - Konsultasi dengan staff\n"
        ),
        color=Color.gold()
    )
    embed.set_footer(text="TALANG SHOP • Klik button di bawah untuk membuka tiket")

    await channel.send(embed=embed, view=OpenTiketView())
    await ctx.send(f"✅ Setup berhasil! Embed tiket sudah dikirim ke {channel.mention}")
    await ctx.message.delete()


# ============================================================
# COMMANDS - SET CHANNEL
# ============================================================
@bot.command(name="setchannel")
@commands.has_permissions(administrator=True)
async def setchannel(ctx):
    embed = Embed(
        title="⚙️ SETUP CHANNEL",
        description=(
            "Silakan mention/tag channel satu per satu.\n"
            "Ketik `skip` untuk melewati.\n\n"
            "**Siap? Mari mulai setup!**"
        ),
        color=Color.blue()
    )
    await ctx.send(embed=embed)

    channels_to_set = [
        ("CHANNEL_OPEN_TIKET_ID", "🎫 Channel Open Tiket", "#open-tiket"),
        ("CHANNEL_NOTIFIKASI_ID", "🔔 Channel Notifikasi", "#notifikasi"),
        ("CHANNEL_REVIEW_ID", "⭐ Channel Review", "#review"),
        ("CHANNEL_PRODUK_STORAGE_ID", "📦 Channel Produk Storage", "#produk-storage"),
        ("CHANNEL_PROGRES_TIKET_ID", "📊 Channel Progres Tiket", "#progres-tiket"),
    ]

    categories_to_set = [
        ("CATEGORY_SHOP_ID", "🛒 Category Shop", "🛒 SHOP"),
        ("CATEGORY_OWNER_PANEL_ID", "🔒 Category Owner Panel", "🔒 OWNER PANEL"),
        ("CATEGORY_TIKET_ID", "📁 Category Tiket Aktif", "📁 TIKET AKTIF"),
    ]

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # Set channels
    for key, label, example in channels_to_set:
        await ctx.send(f"📝 Mention channel untuk **{label}** (contoh: {example}):")
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            if msg.content.lower() == "skip":
                await ctx.send(f"⏭️ {label} dilewati.")
                continue
            if msg.channel_mentions:
                config[key] = msg.channel_mentions[0].id
                save_config(config)
                await ctx.send(f"✅ {label} diset ke {msg.channel_mentions[0].mention}")
            else:
                await ctx.send(f"❌ Format salah. Silakan mention channel dengan #.")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Jalankan `!setchannel` lagi.")
            return

    # Set categories
    for key, label, example in categories_to_set:
        await ctx.send(f"📝 Ketik **ID** category untuk **{label}** (contoh: `{example}`).\n"
                       f"💡 Cara dapat ID: Klik kanan category → Copy ID")
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            if msg.content.lower() == "skip":
                await ctx.send(f"⏭️ {label} dilewati.")
                continue
            try:
                cat_id = int(msg.content.strip())
                category = ctx.guild.get_channel(cat_id)
                if category:
                    config[key] = cat_id
                    save_config(config)
                    await ctx.send(f"✅ {label} diset ke **{category.name}**")
                else:
                    await ctx.send(f"❌ Category dengan ID {cat_id} tidak ditemukan!")
            except ValueError:
                await ctx.send("❌ Masukkan angka ID yang valid!")
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Jalankan `!setchannel` lagi.")
            return

    done_embed = Embed(
        title="✅ SETUP CHANNEL SELESAI!",
        description="Semua channel sudah dikonfigurasi.\nSekarang jalankan `!setup` untuk membuat embed open tiket.",
        color=Color.green()
    )
    await ctx.send(embed=done_embed)


# ============================================================
# COMMANDS - SET QRIS
# ============================================================
@bot.command(name="setqris")
@commands.has_permissions(administrator=True)
async def setqris(ctx):
    await ctx.send("📱 Upload gambar QRIS kamu atau kirim URL gambar QRIS:")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.attachments:
            # Upload attachment dan simpan URL
            url = msg.attachments[0].url
            config["QRIS_IMAGE_URL"] = url
            save_config(config)
            await ctx.send(f"✅ QRIS berhasil diset!")
        elif msg.content.startswith("http"):
            config["QRIS_IMAGE_URL"] = msg.content.strip()
            save_config(config)
            await ctx.send(f"✅ QRIS berhasil diset!")
        else:
            await ctx.send("❌ Kirim gambar atau URL yang valid!")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")


# ============================================================
# COMMANDS - ADD PRODUK
# ============================================================
@bot.command(name="addproduk")
@commands.has_permissions(administrator=True)
async def addproduk(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("📦 **TAMBAH PRODUK BARU**\n\n📝 Masukkan **nama produk**:")

    try:
        # Nama
        msg = await bot.wait_for("message", check=check, timeout=60)
        nama = msg.content.strip()

        # Harga
        await ctx.send(f"💰 Masukkan **harga** untuk **{nama}** (angka saja, contoh: 25000):")
        msg = await bot.wait_for("message", check=check, timeout=60)
        try:
            harga = int(msg.content.strip())
        except ValueError:
            await ctx.send("❌ Harga harus berupa angka!")
            return

        # Stok
        await ctx.send(f"📊 Masukkan **stok** untuk **{nama}**:")
        msg = await bot.wait_for("message", check=check, timeout=60)
        try:
            stok = int(msg.content.strip())
        except ValueError:
            await ctx.send("❌ Stok harus berupa angka!")
            return

        # File
        await ctx.send(f"📎 Upload **file .rbxm** untuk **{nama}**:")
        msg = await bot.wait_for("message", check=check, timeout=120)
        if not msg.attachments:
            await ctx.send("❌ Kamu harus upload file!")
            return

        attachment = msg.attachments[0]
        if not attachment.filename.endswith(".rbxm"):
            await ctx.send("❌ File harus berformat **.rbxm**!")
            return

        # Simpan file ke #produk-storage
        storage_channel_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
        if not storage_channel_id:
            await ctx.send("❌ Channel produk-storage belum diset! Jalankan `!setchannel` dulu.")
            return

        storage_channel = ctx.guild.get_channel(int(storage_channel_id))
        if not storage_channel:
            await ctx.send("❌ Channel produk-storage tidak ditemukan!")
            return

        file_data = await attachment.read()

        storage_embed = Embed(
            title=f"📁 PRODUK: {nama}",
            color=Color.blue()
        )
        storage_embed.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
        storage_embed.add_field(name="📊 Stok", value=str(stok), inline=True)

        storage_msg = await storage_channel.send(
            embed=storage_embed,
            file=discord.File(fp=__import__('io').BytesIO(file_data), filename=attachment.filename)
        )

        # Save to DB
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "INSERT INTO produk (nama, harga, stok, file_message_id) VALUES (?, ?, ?, ?)",
                (nama, harga, stok, storage_msg.id)
            )
            await db.commit()

        success_embed = Embed(
            title="✅ PRODUK BERHASIL DITAMBAHKAN!",
            color=Color.green()
        )
        success_embed.add_field(name="📦 Nama", value=nama, inline=True)
        success_embed.add_field(name="💰 Harga", value=format_rupiah(harga), inline=True)
        success_embed.add_field(name="📊 Stok", value=str(stok), inline=True)
        success_embed.add_field(name="📎 File", value=attachment.filename, inline=True)

        await ctx.send(embed=success_embed)

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout! Jalankan `!addproduk` lagi.")


# ============================================================
# COMMANDS - LIST PRODUK
# ============================================================
@bot.command(name="listproduk")
@commands.has_permissions(administrator=True)
async def listproduk(ctx):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, nama, harga, stok, active FROM produk") as cursor:
            products = await cursor.fetchall()

    if not products:
        await ctx.send("❌ Belum ada produk!")
        return

    embed = Embed(
        title="📦 DAFTAR SEMUA PRODUK",
        color=Color.blue(),
        timestamp=datetime.now()
    )

    for prod in products:
        prod_id, nama, harga, stok, active = prod
        status = "✅ Aktif" if active else "❌ Nonaktif"
        embed.add_field(
            name=f"#{prod_id} - {nama}",
            value=f"💰 {format_rupiah(harga)} | 📊 Stok: {stok} | {status}",
            inline=False
        )

    embed.set_footer(text="TALANG SHOP")
    await ctx.send(embed=embed)


# ============================================================
# COMMANDS - EDIT PRODUK
# ============================================================
@bot.command(name="editproduk")
@commands.has_permissions(administrator=True)
async def editproduk(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    # Tampilkan list produk dulu
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, nama, harga, stok FROM produk WHERE active = 1") as cursor:
            products = await cursor.fetchall()

    if not products:
        await ctx.send("❌ Belum ada produk!")
        return

    list_text = ""
    for p in products:
        list_text += f"**#{p[0]}** - {p[1]} | {format_rupiah(p[2])} | Stok: {p[3]}\n"

    await ctx.send(f"📦 **DAFTAR PRODUK:**\n{list_text}\n📝 Masukkan **ID produk** yang ingin diedit:")

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        prod_id = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT nama, harga, stok FROM produk WHERE id = ?", (prod_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await ctx.send("❌ Produk tidak ditemukan!")
                    return

        await ctx.send(
            f"📝 Apa yang ingin diedit?\n"
            f"1️⃣ Nama (sekarang: **{row[0]}**)\n"
            f"2️⃣ Harga (sekarang: **{format_rupiah(row[1])}**)\n"
            f"3️⃣ Stok (sekarang: **{row[2]}**)\n"
            f"4️⃣ File .rbxm\n\n"
            f"Ketik angka (1/2/3/4):"
        )

        msg = await bot.wait_for("message", check=check, timeout=60)
        choice = msg.content.strip()

        if choice == "1":
            await ctx.send("📝 Masukkan **nama baru**:")
            msg = await bot.wait_for("message", check=check, timeout=60)
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("UPDATE produk SET nama = ? WHERE id = ?", (msg.content.strip(), prod_id))
                await db.commit()
            await ctx.send(f"✅ Nama produk #{prod_id} diubah menjadi **{msg.content.strip()}**")

        elif choice == "2":
            await ctx.send("💰 Masukkan **harga baru** (angka saja):")
            msg = await bot.wait_for("message", check=check, timeout=60)
            try:
                new_harga = int(msg.content.strip())
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute("UPDATE produk SET harga = ? WHERE id = ?", (new_harga, prod_id))
                    await db.commit()
                await ctx.send(f"✅ Harga produk #{prod_id} diubah menjadi **{format_rupiah(new_harga)}**")
            except ValueError:
                await ctx.send("❌ Harga harus berupa angka!")

        elif choice == "3":
            await ctx.send("📊 Masukkan **stok baru**:")
            msg = await bot.wait_for("message", check=check, timeout=60)
            try:
                new_stok = int(msg.content.strip())
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute("UPDATE produk SET stok = ? WHERE id = ?", (new_stok, prod_id))
                    await db.commit()
                await ctx.send(f"✅ Stok produk #{prod_id} diubah menjadi **{new_stok}**")
            except ValueError:
                await ctx.send("❌ Stok harus berupa angka!")

        elif choice == "4":
            await ctx.send("📎 Upload **file .rbxm baru**:")
            msg = await bot.wait_for("message", check=check, timeout=120)
            if not msg.attachments or not msg.attachments[0].filename.endswith(".rbxm"):
                await ctx.send("❌ Upload file .rbxm yang valid!")
                return

            storage_channel_id = config.get("CHANNEL_PRODUK_STORAGE_ID")
            storage_channel = ctx.guild.get_channel(int(storage_channel_id))

            if not storage_channel:
                await ctx.send("❌ Channel produk-storage tidak ditemukan!")
                return

            file_data = await msg.attachments[0].read()
            storage_msg = await storage_channel.send(
                content=f"📁 UPDATE FILE - Produk #{prod_id}",
                file=discord.File(fp=__import__('io').BytesIO(file_data), filename=msg.attachments[0].filename)
            )

            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("UPDATE produk SET file_message_id = ? WHERE id = ?", (storage_msg.id, prod_id))
                await db.commit()

            await ctx.send(f"✅ File produk #{prod_id} berhasil diupdate!")

        else:
            await ctx.send("❌ Pilihan tidak valid!")

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka ID yang valid!")


# ============================================================
# COMMANDS - DELETE PRODUK
# ============================================================
@bot.command(name="delproduk")
@commands.has_permissions(administrator=True)
async def delproduk(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, nama, harga FROM produk WHERE active = 1") as cursor:
            products = await cursor.fetchall()

    if not products:
        await ctx.send("❌ Tidak ada produk aktif!")
        return

    list_text = ""
    for p in products:
        list_text += f"**#{p[0]}** - {p[1]} | {format_rupiah(p[2])}\n"

    await ctx.send(f"📦 **DAFTAR PRODUK:**\n{list_text}\n🗑️ Masukkan **ID produk** yang ingin dihapus:")

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        prod_id = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT nama FROM produk WHERE id = ?", (prod_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await ctx.send("❌ Produk tidak ditemukan!")
                    return

            await db.execute("UPDATE produk SET active = 0 WHERE id = ?", (prod_id,))
            await db.commit()

        await ctx.send(f"✅ Produk **{row[0]}** (#{prod_id}) berhasil dihapus!")

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka ID yang valid!")


# ============================================================
# COMMANDS - UPDATE STOK
# ============================================================
@bot.command(name="stok")
@commands.has_permissions(administrator=True)
async def update_stok(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT id, nama, stok FROM produk WHERE active = 1") as cursor:
            products = await cursor.fetchall()

    if not products:
        await ctx.send("❌ Tidak ada produk!")
        return

    list_text = ""
    for p in products:
        list_text += f"**#{p[0]}** - {p[1]} | Stok: {p[2]}\n"

    await ctx.send(f"📊 **STOK PRODUK:**\n{list_text}\n📝 Masukkan **ID produk** yang ingin diupdate stoknya:")

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        prod_id = int(msg.content.strip())

        await ctx.send("📊 Masukkan **stok baru**:")
        msg = await bot.wait_for("message", check=check, timeout=60)
        new_stok = int(msg.content.strip())

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT nama FROM produk WHERE id = ?", (prod_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await ctx.send("❌ Produk tidak ditemukan!")
                    return

            await db.execute("UPDATE produk SET stok = ? WHERE id = ?", (new_stok, prod_id))
            await db.commit()

        await ctx.send(f"✅ Stok **{row[0]}** diupdate menjadi **{new_stok}**")

    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout!")
    except ValueError:
        await ctx.send("❌ Masukkan angka yang valid!")


# ============================================================
# COMMANDS - HELP
# ============================================================
@bot.command(name="help")
async def help_command(ctx):
    if not is_owner(ctx.author):
        return

    embed = Embed(
        title="📖 TALANG SHOP - COMMAND LIST",
        description="Daftar semua command yang tersedia:",
        color=Color.blue()
    )
    embed.add_field(
        name="⚙️ Setup",
        value=(
            "`!setup` - Setup embed open tiket\n"
            "`!setchannel` - Set semua channel\n"
            "`!setqris` - Set gambar QRIS\n"
        ),
        inline=False
    )
    embed.add_field(
        name="📦 Produk",
        value=(
            "`!addproduk` - Tambah produk baru\n"
            "`!editproduk` - Edit produk\n"
            "`!delproduk` - Hapus produk\n"
            "`!listproduk` - Lihat semua produk\n"
            "`!stok` - Update stok produk\n"
        ),
        inline=False
    )
    embed.set_footer(text="TALANG SHOP • Hanya OWNER yang bisa menggunakan command ini")
    await ctx.send(embed=embed)


# ============================================================
# EVENTS
# ============================================================
@bot.event
async def on_ready():
    await init_db()
    bot.add_view(OpenTiketView())
    print(f"{'='*50}")
    print(f"  🤖 {config['BOT_NAME']} is ONLINE!")
    print(f"  📌 Logged in as: {bot.user}")
    print(f"  📌 Bot ID: {bot.user.id}")
    print(f"  📌 Prefix: {config['PREFIX']}")
    print(f"{'='*50}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Kamu tidak punya izin untuk menggunakan command ini!")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        raise error


# ============================================================
# RUN BOT
# ============================================================
if __name__ == "__main__":
    token = config.get("TOKEN", "")
    if token == "MASUKKAN_TOKEN_BOT_KAMU_DISINI" or not token:
        print("❌ TOKEN belum diisi! Buka config.json dan masukkan token bot kamu.")
    else:
        bot.run(token)
