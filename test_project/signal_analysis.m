%% 信号分析模块 - 演示MATLAB函数调用关系
%  包含多个函数，展示数据采集、分析和可视化流程

function signal_analysis()
    %% 主函数 - 信号分析入口
    data = generate_test_signal(1000);
    filtered = lowpass_filter(data, 0.1);
    peaks = find_peaks(filtered);
    stats = compute_statistics(filtered);
    plot_results(data, filtered, peaks, stats);
end

function signal = generate_test_signal(n_samples)
    %% 生成测试信号
    t = linspace(0, 1, n_samples);
    signal = sin(2 * pi * 10 * t) + 0.5 * randn(1, n_samples);
    signal = normalise(signal);
end

function normalised = normalise(data)
    %% 信号归一化
    max_val = max(data);
    min_val = min(data);
    normalised = (data - min_val) / (max_val - min_val);
end

function filtered = lowpass_filter(data, cutoff)
    %% 低通滤波器
    % 简单移动平均滤波
    window_size = round(1 / cutoff);
    if mod(window_size, 2) == 0
        window_size = window_size + 1;
    end
    filtered = moving_average(data, window_size);
end

function result = moving_average(data, window_size)
    %% 移动平均
    half = floor(window_size / 2);
    n = length(data);
    result = zeros(1, n);

    for i = 1:n
        start_idx = max(1, i - half);
        end_idx = min(n, i + half);
        result(i) = mean_value(data(start_idx:end_idx));
    end
end

function m = mean_value(x)
    %% 计算均值
    m = sum(x) / length(x);
end

function peaks = find_peaks(data)
    %% 查找信号峰值
    peaks = [];
    for i = 2:length(data)-1
        if is_peak(data, i)
            peaks = [peaks, i];
        end
    end
end

function result = is_peak(data, idx)
    %% 判断是否为峰值
    result = data(idx) > data(idx-1) && data(idx) > data(idx+1);
end

function stats = compute_statistics(data)
    %% 计算信号统计特征
    stats.mean = mean_value(data);
    stats.max = max(data);
    stats.min = min(data);
    stats.std = std_dev(data);
end

function s = std_dev(data)
    %% 计算标准差
    m = mean_value(data);
    squared_diff = (data - m).^2;
    s = sqrt(mean_value(squared_diff));
end

function plot_results(data, filtered, peaks, stats)
    %% 绘制结果
    figure;

    subplot(2, 1, 1);
    plot(data);
    hold on;
    plot(filtered);
    title('原始信号与滤波后信号');
    legend('原始', '滤波后');

    subplot(2, 1, 2);
    plot(filtered);
    hold on;
    plot(peaks, filtered(peaks), 'ro');
    title(sprintf('峰值检测 (峰值数: %d)', length(peaks)));

    % 输出统计信息
    disp_stats(stats);
end

function disp_stats(stats)
    %% 显示统计信息
    fprintf('均值: %.4f\n', stats.mean);
    fprintf('最大值: %.4f\n', stats.max);
    fprintf('最小值: %.4f\n', stats.min);
    fprintf('标准差: %.4f\n', stats.std);
end
