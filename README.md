# Phân tích Hiệu suất Nhân viên theo Quy trình BPMN

Ứng dụng desktop (Tkinter, chạy được trên Windows và macOS) tính **hiệu suất của từng nhân viên theo từng loại task**, dựa trên file BPMN (quy trình chuẩn), eventlog (nhật ký thực thi) và standard time (SLA từng task).

## 🚀 Chạy ứng dụng (chỉ cần nhấn đúp)

Yêu cầu máy đã cài **Python 3.9+** (tải tại [python.org](https://www.python.org/downloads/); trên Windows nhớ tick **"Add Python to PATH"** khi cài).

| Hệ điều hành | Việc cần làm |
|---|---|
| **macOS** | Nhấn đúp vào [`run_mac.command`](run_mac.command). Nếu bị chặn vì "không rõ nhà phát triển": chuột phải (Control-click) vào file → **Open** → xác nhận **Open** lần nữa. |
| **Windows** | Nhấn đúp vào [`run_windows.bat`](run_windows.bat). |

Lần đầu chạy sẽ tự tạo môi trường ảo (`.venv`) và tự cài thư viện cần thiết (mất khoảng 1 phút, cần có mạng). Từ lần thứ 2 trở đi ứng dụng mở lên gần như ngay lập tức. Có thể thử ngay với dữ liệu mẫu trong [`sample_data/`](sample_data).

Muốn chạy bằng dòng lệnh (chế độ phát triển) hoặc đóng gói thành app cài đặt độc lập → xem [Dành cho lập trình viên](#dành-cho-lập-trình-viên) ở cuối file.

## Quy trình sử dụng: 2 bước bắt buộc

**File BPMN là nguồn chuẩn (source of truth).** Ứng dụng luôn đi qua 2 bước theo thứ tự:

1. **① Kiểm tra dữ liệu** — đối chiếu eventlog.csv và standardTime.csv với file BPMN, không chạy tính toán đầy đủ. Báo cáo gồm:
   - **Lỗi**: vấn đề chắc chắn ảnh hưởng tới kết quả (vd. eventlog không đọc được dòng nào, endTime sớm hơn startTime, standardTime.csv không có dòng hợp lệ nào).
   - **Cảnh báo**: task trong eventlog không khớp BPMN, task BPMN chưa từng xuất hiện trong eventlog, task chưa có Standard Time tương ứng, dòng standardTime.csv không khớp task nào trong BPMN.
   - **Thông tin**: dòng standardTime.csv được khai báo nhưng chưa dùng đến (không chặn tính toán).

   cùng số liệu tổng quan (số task BPMN, số sự kiện/case/nhân viên trong eventlog, số dòng standardTime).

2. **② Tính hiệu suất** — chỉ **bật** khi bước kiểm tra ở trên không còn **Lỗi** (Cảnh báo và Thông tin không chặn — vd. "1 task BPMN chưa từng xuất hiện trong eventlog" chỉ là lưu ý, có thể do task đó nằm trên nhánh rẽ tùy chọn/loại trừ lẫn nhau của BPMN mà lô dữ liệu hiện tại không đi qua, không hẳn là dữ liệu sai). Nếu vẫn còn Lỗi, nút này vẫn bị khoá; bạn cần sửa file rồi bấm "① Kiểm tra dữ liệu" lại. Kết quả kiểm tra đạt sẽ được ứng dụng cache lại nên bấm "② Tính hiệu suất" không phải đọc/ánh xạ cột lại từ đầu. Nếu đổi bất kỳ file nào trong 3 file đầu vào (BPMN, eventlog, standardTime), kết quả kiểm tra cũ sẽ bị huỷ và bạn phải kiểm tra lại.

## Tính năng

Kết quả tính hiệu suất hiển thị dạng bảng (2 tab: chi tiết theo Nhân viên+Task, và tổng hợp theo Nhân viên), gồm số lượng công việc đã xử lý, thời gian chuẩn trung bình, số lần đúng/trễ hạn và **tỷ lệ trễ hạn (%)** — có thể xuất ra CSV hoặc Excel.

### Phát hiện task bị bỏ sót (tab "Task bị bỏ sót")

Mỗi lần bấm **"① Kiểm tra dữ liệu"**, ứng dụng còn đối chiếu **trình tự** các task trong từng case (eventlog) với **trình tự chuẩn suy ra từ sequenceFlow trong file BPMN** để phát hiện trường hợp một task bị bỏ sót giữa quy trình — dấu hiệu ai đó đã quên chuyển tiếp công việc.

Quy tắc: nếu task liền trước T (theo BPMN) đã được thực hiện xong trong case đó, nhưng task T lại không hề xuất hiện trong case, ứng dụng coi đây là bất thường và **chỉ đích danh nhân viên đã hoàn thành task liền trước** (người có khả năng cao nhất đã bỏ sót/quên chuyển tiếp), kèm:

- Case bị ảnh hưởng
- Tên task bị thiếu
- Tên task liền trước đã hoàn thành, và thời điểm hoàn thành
- Danh sách toàn bộ nhân viên đã tham gia xử lý case đó

Bảng "Theo nhân viên" tổng hợp số lần mỗi nhân viên bị nghi bỏ sót, số case liên quan, và các loại task hay bị bỏ sót nhất.

Tab "Task bị bỏ sót" chỉ **bật** khi bước kiểm tra phát hiện ít nhất 1 trường hợp nghi bỏ sót; nếu dữ liệu sạch (đủ điều kiện tính hiệu suất và không nghi ngờ thiếu task nào), tab này bị khoá vì không có gì để xem.

Nếu case đi theo một nhánh khác của quy trình (ví dụ qua gateway rẽ nhánh) và task liền trước vốn không cần thực hiện, ứng dụng sẽ **không** báo bất thường — chỉ báo khi task liền trước đã chắc chắn xong nhưng bước kế tiếp lại "biến mất".

Nút **"Xuất CSV để bổ sung eventlog..."** trên tab này xuất ra 1 file CSV với đúng các cột của eventlog.csv (`caseId, taskId, activity, startTime, endTime, finishTime, personName`) kèm cột `ghi_chu` giải thích — mỗi dòng là 1 gợi ý task còn thiếu, đã điền sẵn `caseId`/`taskId`/`activity` và nhân viên nghi ngờ phụ trách, `startTime` gợi ý (= lúc hoàn thành task liền trước). Bạn chỉ cần xác nhận lại người thực hiện, điền `endTime`/`finishTime` thực tế rồi dán các dòng đó vào eventlog.csv gốc.

### Mạng xã hội (tab "Mạng xã hội")

Ứng dụng còn dựng **mạng xã hội (social network)** giữa các nhân viên từ chính file `eventlog.csv`, gồm 2 loại:

- **Bàn giao công việc (handover)** — đồ thị có hướng: cạnh A → B nếu A vừa xử lý xong một task trong 1 case thì B xử lý task tiếp theo trong cùng case đó (weight = số lần bàn giao).
- **Cùng xử lý case (collaboration)** — đồ thị vô hướng: cạnh A - B nếu A và B từng cùng tham gia xử lý chung một case (weight = số case chung).

Mỗi loại mạng được vẽ trực quan (kích thước nút theo độ trung tâm, độ dày cạnh theo số lượt tương tác) kèm bảng chỉ số chi tiết theo từng nhân viên (in/out-degree, độ trung tâm bậc, trung gian, gần, PageRank) và các chỉ số tổng quan toàn mạng: số nút/cạnh, mật độ, liên thông, cùng **3 nhân viên nổi bật nhất** theo từng loại độ trung tâm — trung tâm nhất (Degree: kết nối nhiều nhất), trung gian nhiều nhất (Betweenness: cầu nối giữa các nhóm, dễ thành nút thắt cổ chai) và gần trung tâm nhất (Closeness: tiếp cận người khác nhanh nhất trong mạng).

## Định dạng file đầu vào

Ứng dụng nhận 3 file:

1. **File BPMN** (`.bpmn`) — định nghĩa quy trình, dùng để xác định danh sách các Task hợp lệ (id, tên, loại: userTask/serviceTask/...).
2. **Eventlog** (`.csv`) — nhật ký thực thi quy trình: mỗi dòng là một lần thực hiện một task, gồm case, activity (task), resource (nhân viên), thời gian bắt đầu/kết thúc.
3. **Standard Time** (`.csv`) — thời gian chuẩn (SLA) cho từng loại task.

### 1. File BPMN
File BPMN 2.0 chuẩn (xuất từ Camunda Modeler, bpmn.io, Signavio, Bizagi...). Ứng dụng lấy tất cả `<task>`, `<userTask>`, `<serviceTask>`, `<scriptTask>`, `<manualTask>`, `<businessRuleTask>`, `<sendTask>`, `<receiveTask>`, `<callActivity>`, `<subProcess>` cùng thuộc tính `id`/`name`.

### 2. eventlog.csv
Hỗ trợ 2 định dạng, ứng dụng tự nhận diện cột (không phân biệt hoa/thường, tiếng Anh/Việt, cả `snake_case` lẫn `camelCase`); nếu không nhận diện được sẽ hiện hộp thoại để bạn chọn cột thủ công.

**Định dạng rộng (khuyên dùng)** — mỗi dòng là 1 lần thực hiện task. Cột `taskId` là tùy chọn nhưng **nên có**: khi có, ứng dụng đối chiếu chính xác với id Task trong BPMN thay vì chỉ so tên activity (tránh nhầm lẫn khi nhiều task trùng tên). Cột `finishTime` (thời lượng đã tính sẵn, dạng "194 phút") là tùy chọn và **không** được dùng để suy ra mốc kết thúc — ứng dụng luôn tính thời gian thực tế từ `startTime`/`endTime`.

```csv
caseId,taskId,activity,startTime,endTime,finishTime,personName
CASE0001,T0001,Tiếp nhận đơn hàng,2026-09-16 20:18:35,2026-09-16 23:32:35,194 phút,Nguyễn Văn A
CASE0001,T0002,Kiểm tra tồn kho,2026-09-16 23:42:35,2026-09-17 00:44:35,62 phút,Trần Thị B
CASE0001,T0003,Xác nhận thanh toán,2026-09-17 01:33:35,2026-09-17 04:31:35,178 phút,Hoàng Thị E
```

Các tên cột tương đương cũng được tự nhận diện, ví dụ: `case_id`/`caseId`, `resource`/`personName`/`nhân viên`, `start_time`/`startTime`, `end_time`/`endTime`, `task_id`/`taskId`/`mã task`.

**Định dạng dài** (mỗi dòng là 1 sự kiện lifecycle, ví dụ export từ XES):
```csv
case_id,activity,resource,timestamp,lifecycle:transition
Case_001,Tiếp nhận đơn,Nguyen Van A,2026-09-01 08:00,start
Case_001,Tiếp nhận đơn,Nguyen Van A,2026-09-01 08:12,complete
```
(ứng dụng sẽ tự ghép cặp start/complete theo thứ tự xuất hiện trong mỗi case+task_id/activity)

### 3. standardTime.csv
```csv
taskId,task,standard_time,unit
T0001,Tiếp nhận đơn hàng,15,minutes
T0002,Kiểm tra tồn kho,45,minutes
```
Cột `unit` (minutes/hours/days) không bắt buộc — nếu thiếu, bạn chọn đơn vị mặc định trong hộp thoại ánh xạ cột. Cột `taskId` cũng tùy chọn.

`task` nên trùng với tên (hoặc id) task trong file BPMN để việc đối chiếu chính xác; nếu cả eventlog và standardTime đều có `taskId`, ứng dụng ưu tiên đối chiếu theo id (chính xác hơn so tên).

## Cấu trúc dự án

```
bpm_performance_app/
  run_mac.command             # nhấn đúp để chạy trên macOS (tự cài đặt lần đầu)
  run_windows.bat              # nhấn đúp để chạy trên Windows (tự cài đặt lần đầu)
  main.py                      # điểm khởi chạy (dùng khi chạy bằng dòng lệnh)
  requirements.txt
  README.md
  core/                        # logic xử lý, không phụ thuộc GUI
    bpmn_parser.py              # đọc file .bpmn, lấy danh sách Task + quan hệ trình tự
    data_loader.py              # đọc & chuẩn hoá eventlog.csv, standardTime.csv
    analyzer.py                 # tính toán hiệu suất
    validator.py                 # đối chiếu BPMN / eventlog / standardTime
    gap_analysis.py              # phát hiện task bị bỏ sót theo case
    social_network.py            # dựng mạng xã hội + chỉ số SNA từ eventlog
  gui/                         # giao diện Tkinter
    app.py                       # cửa sổ chính
    column_mapping_dialog.py     # hộp thoại ánh xạ cột khi không tự nhận diện được
    network_view.py              # tab vẽ mạng xã hội + bảng chỉ số
  sample_data/                 # dữ liệu mẫu để thử nghiệm
  packaging/                   # đóng gói thành ứng dụng độc lập (chỉ dành cho dev)
    build_mac.sh                 # đóng gói .app cho macOS (chạy trên máy Mac)
    build_windows.bat            # đóng gói .exe cho Windows (chạy trên máy Windows)
```

## Giới hạn hiện tại

- Nếu một task được thực hiện nhiều lần trong cùng 1 case ở định dạng "dài", việc ghép cặp start/complete dựa trên thứ tự xuất hiện — dữ liệu lồng nhau bất thường có thể ghép sai; nên dùng định dạng "rộng" nếu có thể.
- Task trong eventlog không khớp với BPMN (theo id lẫn tên) vẫn được tính bình thường, chỉ không dùng được tên/id chuẩn hoá từ BPMN.

## Dành cho lập trình viên

### Chạy bằng dòng lệnh (chế độ phát triển)

Yêu cầu Python 3.9+ có Tkinter (Windows/macOS cài Python từ python.org đã có sẵn Tkinter; trên macOS dùng Homebrew Python thì cần `brew install python-tk`).

```bash
cd bpm_performance_app
python3 -m pip install -r requirements.txt
python3 main.py
```

### Đóng gói thành ứng dụng desktop độc lập

**macOS** (chạy trên máy Mac):
```bash
./packaging/build_mac.sh
```
Kết quả: `dist/HieuSuatNhanVien.app`

**Windows** (chạy trên máy Windows):
```bat
packaging\build_windows.bat
```
Kết quả: `dist\HieuSuatNhanVien\HieuSuatNhanVien.exe`

> PyInstaller phải được build trên đúng hệ điều hành đích (build trên Mac ra file `.app`, build trên Windows ra file `.exe`) — không cross-compile được.
