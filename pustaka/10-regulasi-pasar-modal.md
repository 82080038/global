# Regulasi Pasar Modal

> **Tujuan:** Dokumen ini adalah referensi komprehensif tentang regulasi pasar modal — Indonesia dan global — yang penting untuk membangun aplikasi yang compliant.

---

## Daftar Isi

1. [Regulasi Pasar Modal Indonesia](#1-regulasi-pasar-modal-indonesia)
2. [OJK dan Pengawasan](#2-ojk-dan-pengawasan)
3. [Peraturan BEI](#3-peraturan-bei)
4. [Perlindungan Investor](#4-perlindungan-investor)
5. [Regulasi Global](#5-regulasi-global)
6. [Regulasi Teknologi dan Fintech](#6-regulasi-teknologi-dan-fintech)
7. [Compliance untuk Aplikasi](#7-compliance-untuk-aplikasi)

---

## 1. Regulasi Pasar Modal Indonesia

### 1.1 Hierarki Hukum

```
1. Undang-Undang (UU)
   ├── UU No. 8 Tahun 1995 tentang Pasar Modal
   └── UU No. 4 Tahun 2023 (Penguatan & Pengembangan Sektor Keuangan)
   
2. Peraturan Pemerintah (PP)
   
3. Peraturan OJK (POJK)
   ├── POJK tentang Penyelenggaraan Usaha Perusahaan Efek
   ├── POJK tentang Manajer Investasi
   ├── POJK tentang Emiten
   └── POJK tentang Perlindungan Investor
   
4. Peraturan Bursa (BEI)
   ├── I-B (Perdagangan Efek)
   ├── I-E (Pencatatan Efek)
   └── I-X (Sanksi)
   
5. Peraturan KPEI dan KSEI
```

### 1.2 UU No. 8 Tahun 1995 — Poin Penting

| Pasal | Isi |
|-------|-----|
| **Pasal 1** | Definisi pasar modal, efek, emiten |
| **Pasal 3** | Efek yang dapat diperdagangkan |
| **Pasal 4-10** | Penawaran umum (IPO) |
| **Pasal 11-20** | Emiten dan perusahaan publik |
| **Pasal 21-30** | Perusahaan efek |
| **Pasal 31-40** | Manajer investasi |
| **Pasal 41-50** | Penjamin emisi efek |
| **Pasal 51-60** | Perantara pedagang efek |
| **Pasal 61-70** | Lembaga dan profesi penunjang |
| **Pasal 71-80** | Bursa efek, kliring, penjaminan, penyimpanan |
| **Pasal 81-90** | Sanksi administratif |
| **Pasal 91-100** | Ketentuan pidana |

### 1.3 UU No. 4 Tahun 2023 — Pembaruan

- Memperbarui UU Pasar Modal (UU No. 8/1995)
- Memperkenalkan konsep **digital assets** dalam definisi efek
- Memperkuat kewenangan OJK
- Mengatur **financial technology** secara eksplisit
- Mengatur **digital financial innovation**
- Memperkenalkan **multiple voting shares** (notasi "N" di BEI)

---

## 2. OJK dan Pengawasan

### 2.1 Kewenangan OJK

Otoritas Jasa Keuangan (OJK) dibentuk berdasarkan **UU No. 21 Tahun 2011**. Kewenangan:

1. **Pengaturan dan pengawasan** sektor jasa keuangan
   - Perbankan
   - Pasar Modal
   - Lembaga Keuangan Non-Bank (IKNB)

2. **Pengawasan integrated** — sebelumnya terpisah (BAPEPAM-LK untuk pasar modal)

3. **Perlindungan konsumen** sektor jasa keuangan

4. **Pendidikan literasi keuangan** masyarakat

### 2.2 POJK Penting untuk Aplikasi

| POJK | Topik | Relevansi |
|------|-------|-----------|
| POJK No. 5/2022 | Tata Kelola Teknologi Informasi | IT governance |
| POJK No. 11/2022 | Data dan Informasi Sektor Jasa Keuangan | Data management |
| POJK No. 13/2023 | Penyelenggaraan Usaha Perusahaan Efek | Securities company |
| POJK No. 16/2023 | Penasihat Investasi | Investment advisor |
| POJK No. 20/2023 | Reksa Dana | Mutual funds |
| POJK No. 27/2023 | Produk Digital Finansial | Digital financial products |
| POJK No. 10/2023 | Layanan Permodalan Berbasis Teknologi (Equity Crowdfunding) | Equity crowdfunding |

---

## 3. Peraturan BEI

### 3.1 Peraturan Nomor I-B (Perdagangan Efek)

Mengatur:
- Sesi perdagangan dan waktu
- Jenis order
- Fraksi harga (tick size)
- Unit transaksi (lot size)
- Auto reject dan circuit breaker
- Short selling dan margin trading
- Negotiated trade

### 3.2 Peraturan Nomor I-E (Pencatatan Efek)

Mengatur:
- Syarat pencatatan (papan utama, pengembangan, akselerasi)
- Dokumen pencatatan
- Kewajiban emiten (disclosure, reporting)
- Corporate actions
- Delisting

### 3.3 Kewajiban Emiten

| Kewajiban | Frekuensi | Deadline |
|-----------|-----------|----------|
| **Laporan Keuangan Tahunan** | Tahunan | 90 hari setelah tahun buku |
| **Laporan Keuangan Semester** | Semesteran | 60 hari setelah semester |
| **Laporan Keuangan Triwulanan** | Triwulanan | 45 hari setelah quarter |
| **Laporan Aksi Korporasi** | Ad hoc | 2 hari kerja |
| **Laporan Pemegang Saham** | Ad hoc | 5 hari kerja |
| **Public Expose** | Tahunan | Minimal 1x per tahun |

### 3.4 Notasi Khusus

| Notasi | Arti | Implikasi |
|--------|------|-----------|
| **X** | Daftar Efek dalam Pemantauan Khusus (DEPK) | Risiko tinggi, monitoring ketat |
| **N** | Multiple Voting Shares | Struktur kontrol khusus |
| **E** | Ekuitas negatif | Delisting warning |
| **S** | Suspend | Tidak dapat diperdagangkan |
| **W** | Warrant | Instrumen derivatif |

---

## 4. Perlindungan Investor

### 4.1 SIPF (Securities Investor Protection Fund)

- Melindungi investor dari kegagalan perusahaan efek
- Maksimum ganti rugi: Rp100 juta per investor
- Didanai oleh iuran perusahaan efek

### 4.2 Sistem Whistleblowing (WBS)

- Pelaporan pelanggaran pasar modal oleh insider
- OJK mengelola WBS
- Perlindungan identitas whistleblower

### 4.3 Investor Warning

OJK mengeluarkan peringatan untuk:
- Investasi bodong (pencatatan tidak sah)
- Penipuan berkedok investasi
- Platform tidak berizin

### 4.4 Edukasi dan Literasi

- Program "Yuk Nabung Saham" (BEI)
- Galeri Investasi (kampus)
- OJK Institute
- Cek-izin OJK untuk verifikasi perusahaan

---

## 5. Regulasi Global

### 5.1 Amerika Serikat

| Regulasi | Badan | Fokus |
|----------|-------|-------|
| **Securities Act 1933** | SEC | Penerbitan efek (IPO) |
| **Securities Exchange Act 1934** | SEC | Perdagangan, bursa, broker |
| **Investment Company Act 1940** | SEC | Reksa dana, ETF |
| **Investment Advisers Act 1940** | SEC | Penasihat investasi |
| **Sarbanes-Oxley Act 2002** | SEC/PCAOB | Corporate governance post-Enron |
| **Dodd-Frank Act 2010** | SEC/CFTC | Post-2008 financial crisis |
| **Regulation NMS** | SEC | National Market System |
| **Regulation Best Interest** | SEC | Broker standard of care |

### 5.2 Eropa

| Regulasi | Fokus |
|----------|-------|
| **MiFID II (2018)** | Transparansi, investor protection, best execution |
| **MiFIR** | Reporting dan transparency |
| **EMIR** | Derivatives reporting dan clearing |
| **PRIIPs** | KIID document untuk produk investasi |
| **GDPR** | Data privacy (berlaku untuk aplikasi dengan user EU) |
| **SFDR** | Sustainable finance disclosure |
| **CSRD** | Corporate sustainability reporting |

### 5.3 Inggris (Post-Brexit)

| Regulasi | Badan | Fokus |
|----------|-------|-------|
| **FSMA 2000** | FCA | Financial Services and Markets Act |
| **UK MiFIR** | FCA | Adapted MiFID II post-Brexit |
| **Consumer Duty** | FCA | Retail investor protection (2023) |

### 5.4 Asia

| Negara | Regulator | Regulasi Utama |
|--------|-----------|----------------|
| **Jepang** | FSA | Financial Instruments and Exchange Act |
| **Singapura** | MAS | Securities and Futures Act |
| **Hong Kong** | SFC | Securities and Futures Ordinance |
| **China** | CSRC | Securities Law of PRC |
| **Korea** | FSC | Financial Investment Services and Capital Markets Act |
| **India** | SEBI | SEBI Act 1992 |
| **Australia** | ASIC | Corporations Act 2001 |

---

## 6. Regulasi Teknologi dan Fintech

### 6.1 Indonesia

| Regulasi | Fokus |
|----------|-------|
| **UU ITE** | Transaksi elektronik |
| **POJK 27/2023** | Produk Digital Finansial |
| **POJK 10/2023** | Equity Crowdfunding |
| **POJK 5/2022** | Tata Kelola TI Sektor Jasa Keuangan |
| **POJK 11/2022** | Data dan Informasi Sektor Jasa Keuangan |
| **PP 71/2019** | Penyelenggaraan Sistem Elektronik |

### 6.2 Global

| Regulasi | Wilayah | Fokus |
|----------|---------|-------|
| **GDPR** | EU/Global | Data privacy |
| **CCPA** | California | Data privacy |
| **PSD2** | EU | Payment services, open banking |
| **FinTech Regulation** | Various | Varies by jurisdiction |

### 6.3 Regulasi AI dalam Keuangan

- **EU AI Act (2024):** Financial AI systems classified as high-risk
- **SEC AI Rule (proposed):** Disclosure of AI use in investment advice
- **OJK POJK (emerging):** AI governance dalam sektor jasa keuangan

### 6.4 Regulasi Crypto/Digital Assets

| Wilayah | Status |
|---------|--------|
| **AS** | SEC/CFTC jurisdiction, evolving |
| **EU** | MiCA (Markets in Crypto-Assets) Regulation 2024 |
| **Indonesia** | Bappebti (Komoditas), bukan OJK — tapi UU 4/2023 mengintegrasikan |
| **China** | Dilarang (trading), CBDC (e-CNY) didukung |

---

## 7. Compliance untuk Aplikasi

### 7.1 Registrasi dan Lisensi

| Aktivitas Aplikasi | Lisensi yang Diperlukan (ID) |
|--------------------|-----------------------------|
| **Menampilkan data pasar** | Tidak perlu lisensi (data publik) |
| **Memberi rekomendasi saham** | Penasihat Investasi (POJK 16/2023) |
| **Menjalankan trading otomatis** | Perusahaan Efek (POJK 13/2023) |
| **Mengelola dana investor** | Manajer Investasi (POJK 20/2023) |
| **Menyediakan platform matching** | Bursa Efek (sangat sulit) |
| **Equity crowdfunding** | Lintasang Permodalan (POJK 10/2023) |
| **Robo-advisor** | Penasihat Investasi + Manajer Investasi |

### 7.2 Data Privacy

```python
# GDPR/Indonesia Personal Data Protection Principles:
1. Consent: User must consent to data collection
2. Purpose limitation: Use data only for stated purpose
3. Data minimization: Collect only necessary data
4. Accuracy: Keep data accurate and up-to-date
5. Storage limitation: Don't keep data longer than needed
6. Security: Protect data with appropriate measures
7. Accountability: Demonstrate compliance
```

### 7.3 Disclosure Requirements

Aplikasi yang memberi rekomendasi/investasi wajib:

1. **Risk disclosure:** "Investasi memiliki risiko kehilangan modal"
2. **Conflict of interest:** Disclose jika aplikasi memiliki interest di saham yang direkomendasikan
3. **Methodology disclosure:** Jelaskan metode analisis yang digunakan
4. **Performance disclosure:** Tampilkan track record (jika ada) dengan caveat
5. **Disclaimer:** "Bukan ajakan untuk membeli/menjual efek tertentu"

### 7.4 Audit Trail

```python
# Setiap keputusan sistem harus tercatat:
audit_entry = {
    "timestamp": "2026-01-15T09:30:00+07:00",
    "ticker": "BBCA.JK",
    "action": "BUY",
    "conviction": 72.5,
    "engine_version": "2.0",
    "weights_version": "default_v1",
    "scores": {
        "technical": 65,
        "fundamental": 80,
        "macro": 70,
        "global": 55,
        "relationship": 40,
        "sentiment": 60,
    },
    "reasons": ["TECHNICAL_STRONG", "FUNDAMENTAL_STRONG", "RELATIONSHIP_WEAK"],
    "data_as_of": "2026-01-14T15:50:00+07:00",
}
```

### 7.5 Best Practices untuk Aplikasi

1. **Disclaimer di setiap rekomendasi**
2. **Risk score untuk setiap saham**
3. **Tidak ada guarantee of returns**
4. **Transparansi metode** (XAI)
5. **Audit trail** untuk setiap keputusan
6. **Data privacy compliance**
7. **Regular security audit**
8. **User education** (literasi pasar modal)
9. **Clear fee structure** (jika ada)
10. **Customer support** dan complaint handling

---

## Referensi

1. UU No. 8 Tahun 1995 tentang Pasar Modal
2. UU No. 4 Tahun 2023 tentang Penguatan dan Pengembangan Sektor Keuangan
3. UU No. 21 Tahun 2011 tentang Otoritas Jasa Keuangan
4. OJK — Buku Saku Pasar Modal 2023
5. BEI — Peraturan I-B dan I-E
6. SEC — Securities Act of 1933, Securities Exchange Act of 1934
7. EU — MiFID II, GDPR, MiCA
8. FCA — Consumer Duty (2023)
9. POJK 5/2022, 11/2022, 13/2023, 16/2023, 20/2023, 27/2023

---

> **Catatan:** Regulasi terus berubah. Selalu konsultasi dengan legal advisor untuk compliance terkini. Untuk implementasi teknis, lihat `11-knowledge-transfer-aplikasi.md` dan `12-panduan-membangun-aplikasi-pasar-modal.md`.
