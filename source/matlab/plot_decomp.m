function plot_decomp(X, y, complete_covfunc, complete_hypers, decomp_list, ...
                     decomp_hypers, log_noise, figname, latex_names, ...
                     full_name, X_mean, X_scale, y_mean, y_scale, max_depth)

% TODO: Assert that the sum of all kernels is the same as the complete kernel.

if nargin < 15; max_depth = numel(decomp_list); end
% if nargin < 15; max_depth = 4; end

% Convert to double in case python saved as integers
X = double(X);
y = double(y);

%%%% TODO - function should accept a mean function
%y = y - mean(y);

left_extend = 0.1;  % What proportion to extend beyond the data range.
right_extend = 0.4;

num_interpolation_points = 2000;

x_left = min(X) - (max(X) - min(X))*left_extend;
x_right = max(X) + (max(X) - min(X))*right_extend;
xrange = linspace(x_left, x_right, num_interpolation_points)';
xrange_no_extrap = linspace(min(X), max(X), num_interpolation_points)';

noise_var = exp(2*log_noise);
complete_sigma = feval(complete_covfunc{:}, complete_hypers, X, X) + eye(length(y)).*noise_var;
complete_sigmastar = feval(complete_covfunc{:}, complete_hypers, X, xrange);
complete_sigmastarstart = feval(complete_covfunc{:}, complete_hypers, xrange, xrange);

% First, plot the data
complete_mean = complete_sigmastar' / complete_sigma * y;
complete_var = diag(complete_sigmastarstart - complete_sigmastar' / complete_sigma * complete_sigmastar);
posterior_sigma = complete_sigmastarstart - complete_sigmastar' / complete_sigma * complete_sigmastar;
    
figure(1); clf; hold on;
mean_var_plot( X*X_scale+X_mean, y*y_scale+y_mean, ...
               xrange*X_scale+X_mean, complete_mean*y_scale+y_mean, ...
               2.*sqrt(complete_var)*y_scale, false, true); % Only plot the data


title('Raw data');
filename = sprintf('%s_raw_data.fig', figname);
saveas( gcf, filename );

% Now plot the posterior
figure(2); clf; hold on;
mean_var_plot( X*X_scale+X_mean, y*y_scale+y_mean, ...
               xrange*X_scale+X_mean, complete_mean*y_scale+y_mean, ...
               2.*sqrt(complete_var)*y_scale, false, false);

% Remove outer brackets and extra latex markup from name.
if iscell(full_name); full_name = full_name{1}; end
full_name = strrep(full_name, '\left', '');
full_name = strrep(full_name, '\right', '');
%title(full_name);
title('Full model posterior with extrapolations');
filename = sprintf('%s_all.fig', figname);
saveas( gcf, filename );

% Now plot samples from the posterior
figure(3); clf; hold on;
sample_plot( X*X_scale+X_mean, xrange*X_scale+X_mean, complete_mean*y_scale+y_mean, ...
               posterior_sigma);

% Remove outer brackets and extra latex markup from name.
if iscell(full_name); full_name = full_name{1}; end
full_name = strrep(full_name, '\left', '');
full_name = strrep(full_name, '\right', '');
%title(full_name);
title('Random samples from the full model posterior');
filename = sprintf('%s_all_sample.fig', figname);
saveas( gcf, filename );

% Then plot the same thing, but just the end.
% complete_mean = complete_sigmastar' / complete_sigma * y;
% complete_var = diag(complete_sigmastarstart - complete_sigmastar' / complete_sigma * complete_sigmastar);
%     
% figure(100); clf; hold on;
% mean_var_plot(X*X_scale+X_mean, y*y_scale+y_mean, xrange*X_scale+X_mean, complete_mean*y_scale+y_mean, 2.*sqrt(complete_var)*y_scale, true, false);
% title(full_name);
% filename = sprintf('%s_all_small.fig', figname);
% saveas( gcf, filename );

% Plot residuals.
% figure(1000); clf; hold on;
% data_complete_mean = feval(complete_covfunc{:}, complete_hypers, X, X)' / complete_sigma * y;
% std_ratio = std((y-data_complete_mean)) / sqrt(noise_var);
% mean_var_plot(X*X_scale+X_mean, (y-data_complete_mean)*y_scale, ...
%               xrange*X_scale+X_mean, zeros(size(xrange)), ...
%               2.*sqrt(noise_var).*ones(size(xrange)).*y_scale, false, true);
% title(['Residuals']);
% filename = sprintf('%s_resid.fig', figname);
% saveas( gcf, filename );

% Determine the order to diaplay the components by computing cross validated MAEs

MAEs = NaN(numel(decomp_list), 1);

folds = 10;

X_train = cell(folds,1);
y_train = cell(folds,1);
X_valid = cell(folds,1);
y_valid = cell(folds,1);

%%%% TODO - Check me for overlap

for fold = 1:folds
    range = max(1,floor(length(X)*(fold-1)/folds)):floor(length(X)*(fold)/folds);
    X_valid{fold} = X(range);
    y_valid{fold} = y(range);
    range = [1:min(length(X),floor(length(X)*(fold-1)/folds)-1),...
            max(1,floor(length(X)*(fold)/folds)+1):length(X)];
    X_train{fold} = X(range);
    y_train{fold} = y(range);
end

idx = [];

cum_kernel = cell(0);
cum_hyp = [];

% Precompute some kernels

K_list = cell(numel(decomp_list), 1);
for i = 1:numel(decomp_list)
    cur_cov = decomp_list{i};
    cur_hyp = decomp_hypers{i};
    K_list{i} = feval(cur_cov{:}, cur_hyp, X, X);
end

% Determine if some components are very similar

% component_corr = zeros(numel(decomp_list));
% for i = 1:numel(decomp_list)
%     for j = (i+1):numel(decomp_list)
%         component_corr(i,j) = -mean(diag(K_list{i}*(complete_sigma\K_list{j}))./sqrt(abs(diag(K_list{i} - K_list{i}*(complete_sigma\K_list{i})).*diag(K_list{j} - K_list{j}*(complete_sigma\K_list{j})))));
%     end
% end
% 
% i = 1;
% while i <= numel(decomp_list)
%     j = (i+1);
%     while j <= numel(decomp_list)
%         if component_corr(i, j) < -0.8
%             % Components v. sim. - remove
%             new_idx = [1:(j-1),(j+1):numel(decomp_list)];
%             component_corr = component_corr(new_idx, new_idx);
%             decomp_list{i} = {@covSum, {decomp_list{i}, decomp_list{j}}};
%             decomp_list = decomp_list(new_idx);
%             decomp_hypers{i} = [decomp_hypers{i}, decomp_hypers{j}];
%             decomp_hypers = decomp_hypers(new_idx);
%         else
%             j = j + 1;
%         end
%     end
%     i = i + 1;
% end

MAEs = zeros(numel(decomp_list), 1);
MAE_reductions = zeros(numel(decomp_list), 1);
MAV_data = mean(abs(y));
previous_MAE = MAV_data;

for i = 1:min(numel(decomp_list), max_depth)
    best_MAE = Inf;
    for j = 1:numel(decomp_list)
        if ~sum(j == idx)
            kernels = cum_kernel;
            kernels{i} = decomp_list{j};
            hyps = cum_hyp;
            hyps = [hyps, decomp_hypers{j}];
            hyp.mean = [];
            hyp.cov = hyps;
            cur_cov = {@covSum, kernels};
            e = NaN(length(X_train), 1);
            for fold = 1:length(X_train)
              K = feval(complete_covfunc{:}, complete_hypers, X_train{fold}) + ...
                  noise_var*eye(length(y_train{fold}));
              Ks = feval(cur_cov{:}, hyp.cov, X_train{fold}, X_valid{fold});

              ymu = Ks' * (K \ y_train{fold});

              e(fold) = mean(abs(y_valid{fold} - ymu));
            end
            
            my_MAE = mean(e);
            if my_MAE < best_MAE
                best_j  = j;
                best_MAE = my_MAE;
            end
        end
    end
    MAEs(i) = best_MAE;
    MAE_reductions(i) = (1 - best_MAE / previous_MAE)*100;
    previous_MAE = best_MAE;
    idx = [idx, best_j];
    cum_kernel{i} = decomp_list{best_j};
    cum_hyp = [cum_hyp, decomp_hypers{best_j}];
end

% Plot each component without data

SNRs = zeros(numel(decomp_list),1);
vars = zeros(numel(decomp_list),1);
monotonic = zeros(numel(decomp_list),1);
gradients = zeros(numel(decomp_list),1);

for j = 1:min(numel(decomp_list), max_depth)
    i = idx(j);
    cur_cov = decomp_list{i};
    cur_hyp = decomp_hypers{i};
    
    % Compute mean and variance for this kernel.
    decomp_sigma = feval(cur_cov{:}, cur_hyp, X, X);
    decomp_sigma_star = feval(cur_cov{:}, cur_hyp, X, xrange_no_extrap);
    decomp_sigma_starstar = feval(cur_cov{:}, cur_hyp, xrange_no_extrap, xrange_no_extrap);
    decomp_mean = decomp_sigma_star' / complete_sigma * y;
    decomp_var = diag(decomp_sigma_starstar - decomp_sigma_star' / complete_sigma * decomp_sigma_star);
    
    data_mean = decomp_sigma' / complete_sigma * y;
    diffs = data_mean(2:end) - data_mean(1:(end-1));
    data_var = diag(decomp_sigma - decomp_sigma' / complete_sigma * decomp_sigma);
    SNRs(j) = 10 * log10(sum(data_mean.^2)/sum(data_var));
    vars(j) = (1 - var(y - data_mean) / var(y)) * 100;
    if all(diffs>0)
        monotonic(j) = 1;
    elseif all(diffs<0)
        monotonic(j) = -1;
    else
        monotonic(j) = 0;
    end
    gradients(j) = (data_mean(end) - data_mean(1)) / (X(end) - X(1));
    
    % Compute the remaining signal after removing the mean prediction from all
    % other parts of the kernel.
    removed_mean = y - (complete_sigma - decomp_sigma)' / complete_sigma * y;
    
    figure(i + 1); clf; hold on;
    mean_var_plot( X*X_scale+X_mean, removed_mean*y_scale, ...
                   xrange_no_extrap*X_scale+X_mean, ...
                   decomp_mean*y_scale, 2.*sqrt(decomp_var)*y_scale, false, false, true); % Don't plot data
    
    %set(gca, 'Children', [h_bars, h_mean, h_dots] );
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(latex_names{i});
    title(sprintf('Posterior of component %d', j));
    fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d.fig', figname, j);
    saveas( gcf, filename );
    
    % Compute mean and variance for this kernel.
    decomp_sigma = feval(cur_cov{:}, cur_hyp, X, X);
    decomp_sigma_star = feval(cur_cov{:}, cur_hyp, X, xrange);
    decomp_sigma_starstar = feval(cur_cov{:}, cur_hyp, xrange, xrange);
    decomp_mean = decomp_sigma_star' / complete_sigma * y;
    decomp_sigma_posterior = decomp_sigma_starstar - decomp_sigma_star' / complete_sigma * decomp_sigma_star;
    decomp_var = diag(decomp_sigma_posterior);
    
    data_mean = decomp_sigma' / complete_sigma * y;
    diffs = data_mean(2:end) - data_mean(1:(end-1));
    data_var = diag(decomp_sigma - decomp_sigma' / complete_sigma * decomp_sigma);
    SNRs(j) = 10 * log10(sum(data_mean.^2)/sum(data_var));
    vars(j) = (1 - var(y - data_mean) / var(y)) * 100;
    if all(diffs>0)
        monotonic(j) = 1;
    elseif all(diffs<0)
        monotonic(j) = -1;
    else
        monotonic(j) = 0;
    end
    gradients(j) = (data_mean(end) - data_mean(1)) / (X(end) - X(1));
    
    % Compute the remaining signal after removing the mean prediction from all
    % other parts of the kernel.
    removed_mean = y - (complete_sigma - decomp_sigma)' / complete_sigma * y;
    
    figure(i + 1); clf; hold on;
    mean_var_plot( X*X_scale+X_mean, removed_mean*y_scale, ...
                   xrange*X_scale+X_mean, ...
                   decomp_mean*y_scale, 2.*sqrt(decomp_var)*y_scale, false, false, true); % Don't plot data
    
    %set(gca, 'Children', [h_bars, h_mean, h_dots] );
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(latex_names{i});
    title(sprintf('Posterior of component %d', j));
    fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d_extrap.fig', figname, j);
    saveas( gcf, filename );
    
    figure(i + 1); clf; hold on;
    sample_plot( X*X_scale+X_mean, xrange*X_scale+X_mean, decomp_mean*y_scale, decomp_sigma_posterior )
    
    %set(gca, 'Children', [h_bars, h_mean, h_dots] );
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(latex_names{i});
    title(sprintf('Random samples from the posterior of component %d', j));
    fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d_sample.fig', figname, j);
    saveas( gcf, filename );
end

% Plot cumulative components with data

cum_kernel = cell(0);
cum_hyp = [];

var(y);
resid = y;

cum_SNRs = zeros(numel(decomp_list),1);
cum_vars = zeros(numel(decomp_list),1);
cum_resid_vars = zeros(numel(decomp_list),1);

for j = 1:min(numel(decomp_list), max_depth)
    i = idx(j);
    cum_kernel{j} = decomp_list{i};
    cum_hyp = [cum_hyp, decomp_hypers{i}];
    cur_cov = {@covSum, cum_kernel};
    cur_hyp = cum_hyp;
    
    % Compute mean and variance for this kernel.
    decomp_sigma = feval(cur_cov{:}, cur_hyp, X, X);
    decomp_sigma_star = feval(cur_cov{:}, cur_hyp, X, xrange_no_extrap);
    decomp_sigma_starstar = feval(cur_cov{:}, cur_hyp, xrange_no_extrap, xrange_no_extrap);
    decomp_mean = decomp_sigma_star' / complete_sigma * y;
    decomp_var = diag(decomp_sigma_starstar - decomp_sigma_star' / complete_sigma * decomp_sigma_star);
    
    var(y-decomp_sigma' / complete_sigma * y);    
    
    data_mean = decomp_sigma' / complete_sigma * y;
    data_var = diag(decomp_sigma - decomp_sigma' / complete_sigma * decomp_sigma);
    cum_SNRs(j) = 10 * log10(sum(data_mean.^2)/sum(data_var));
    cum_vars(j) = (1 - var(y - data_mean) / var(y)) * 100;
    cum_resid_vars(j) = (1 - var(y - data_mean) / var(resid)) * 100;
    resid = y - data_mean;
    
    figure(i + 1); clf; hold on;
    mean_var_plot( X*X_scale+X_mean, y*y_scale, ...
                   xrange_no_extrap*X_scale+X_mean, ...
                   decomp_mean*y_scale, 2.*sqrt(decomp_var)*y_scale, false, false);
    
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(['The above + ' latex_names{i}]);
    title(sprintf('Sum of components up to component %d', j));
    %fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d_cum.fig', figname, j);
    saveas( gcf, filename );
    
    % Compute mean and variance for this kernel.
    
    decomp_sigma = feval(cur_cov{:}, cur_hyp, X, X);
    decomp_sigma_star = feval(cur_cov{:}, cur_hyp, X, xrange);
    decomp_sigma_starstar = feval(cur_cov{:}, cur_hyp, xrange, xrange);
    decomp_mean = decomp_sigma_star' / complete_sigma * y;
    decomp_var = diag(decomp_sigma_starstar - decomp_sigma_star' / complete_sigma * decomp_sigma_star);
    
    var(y-decomp_sigma' / complete_sigma * y);    
    
    data_mean = decomp_sigma' / complete_sigma * y;
    data_var = diag(decomp_sigma - decomp_sigma' / complete_sigma * decomp_sigma);
    cum_SNRs(j) = 10 * log10(sum(data_mean.^2)/sum(data_var));
    cum_vars(j) = (1 - var(y - data_mean) / var(y)) * 100;
    cum_resid_vars(j) = (1 - var(y - data_mean) / var(resid)) * 100;
    resid = y - data_mean;
    
    figure(i + 1); clf; hold on;
    mean_var_plot( X*X_scale+X_mean, y*y_scale, ...
                   xrange*X_scale+X_mean, ...
                   decomp_mean*y_scale, 2.*sqrt(decomp_var)*y_scale, false, false);
    
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(['The above + ' latex_names{i}]);
    title(sprintf('Sum of components up to component %d', j));
    %fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d_cum_extrap.fig', figname, j);
    saveas( gcf, filename );
    
    posterior_sigma = decomp_sigma_starstar - decomp_sigma_star' / complete_sigma * decomp_sigma_star;
    figure(i + 1); clf; hold on;
    sample_plot( X*X_scale+X_mean, xrange*X_scale+X_mean, ...
                 decomp_mean*y_scale, posterior_sigma);
    
    latex_names{i} = strrep(latex_names{i}, '\left', '');
    latex_names{i} = strrep(latex_names{i}, '\right', '');
    %title(['The above + ' latex_names{i}]);
    title(sprintf('Random samples from the cumulative posterior', j));
    %fprintf([latex_names{i}, '\n']);
    filename = sprintf('%s_%d_cum_sample.fig', figname, j);
    saveas( gcf, filename );
end

% Save data to file

save(sprintf('%s_decomp_data.mat', figname), 'idx', 'SNRs', 'vars', ...
     'cum_SNRs', 'cum_vars', 'cum_resid_vars', 'MAEs', 'MAV_data', ...
     'MAE_reductions', 'monotonic', 'gradients');
 
% Convert everything to pdf

dirname = fileparts(figname);
files = dir([dirname, '/*.fig']);
for f_ix = 1:numel(files)
    curfile = [dirname, '/', files(f_ix).name];
    h = open(curfile);
    outfile = [dirname, '/', files(f_ix).name];
    pdfname = strrep(outfile, '.fig', '')
    save2pdf( pdfname, gcf, 600, true );
    %export_fig(pdfname, '-pdf');
    close all
end

end


function mean_var_plot( xdata, ydata, xrange, forecast_mu, forecast_scale, small_plot, data_only, no_data )

    if nargin < 6; small_plot = false; end
    if nargin < 7; data_only = false; end
    if nargin < 8; no_data = false; end

    % Figure settings.
    lw = 1.2;
    opacity = 1;
    light_blue = [227 237 255]./255;
    
    if ~data_only
        % Plot confidence bears.
        jbfill( xrange', ...
            forecast_mu' + forecast_scale', ...
            forecast_mu' - forecast_scale', ...
            light_blue, 'none', 1, opacity); hold on;   
    end
    
    
    set(gca,'Layer','top');  % Stop axes from being overridden.
        
    % Plot data.
    %plot( xdata, ydata, 'ko', 'MarkerSize', 2.1, 'MarkerFaceColor', facecol, 'MarkerEdgeColor', facecol ); hold on;    
    %h_dots = line( xdata, ydata, 'Marker', '.', 'MarkerSize', 2, 'MarkerEdgeColor',  [0 0 0], 'MarkerFaceColor', [0 0 0], 'Linestyle', 'none' ); hold on;    
    if ~no_data
        plot( xdata, ydata, 'k.');
    end
 
    if ~data_only
        % Plot mean function.
        plot(xrange, forecast_mu, 'Color', colorbrew(2), 'LineWidth', lw); hold on;
    end
        

    
    %set(gca, 'Children', [h_dots, h_bars, h_mean ] );
    %e1 = (max(xrange) - min(xrange))/300;
    %for i = 1:length(xdata)
    %   line( [xdata(i) - e1, xdata(i) + e1], [ydata(i) + e1, ydata(i) + e1], 'Color', [0 0 0 ], 'LineWidth', 2 );
    %end
    %set_fig_units_cm( 12,6 );   
    %ag_plot_little_circles_no_alpha(xdata, ydata, 0.02, [0 0 0])
    
    % Make plot prettier.
    set(gcf, 'color', 'white');
    set(gca, 'TickDir', 'out');
    
    xlim([min(xrange), max(xrange)]);
    if small_plot
        totalrange = (max(xrange) - min(xrange));
        xlim([min(xrange) + totalrange*0.7, max(xrange) - totalrange*0.05]);
    end    
    
    % Plot a vertical bar to indicate the start of extrapolation.
    if ~all(forecast_mu == 0) && ~(max(xdata) == max(xrange))  % Don't put extrapolation line on residuals plot.
        y_lim = get(gca,'ylim');
        line( [max(xdata), max(xdata)], y_lim, 'Linestyle', '--', 'Color', [0.3 0.3 0.3 ]);
    end 
    
    % Plot a vertical bar to indicate the start of extrapolation.
    if ~all(forecast_mu == 0) && ~(min(xdata) == min(xrange))  % Don't put extrapolation line on residuals plot.
        y_lim = get(gca,'ylim');
        line( [min(xdata), min(xdata)], y_lim, 'Linestyle', '--', 'Color', [0.3 0.3 0.3 ]);
    end 
    
    %set(get(gca,'XLabel'),'Rotation',0,'Interpreter','latex', 'Fontsize', fontsize);
    %set(get(gca,'YLabel'),'Rotation',90,'Interpreter','latex', 'Fontsize', fontsize);
    %set(gca, 'TickDir', 'out')
    
    set_fig_units_cm( 16,8 );
    
    if small_plot
        set_fig_units_cm( 6, 6 );
    end
end

function sample_plot( xdata, xrange, forecast_mu, forecast_sigma )

    % Figure settings.
    lw = 1.2;
    opacity = 1;
    light_blue = [227 237 255]./255;
    
    set(gca,'Layer','top');  % Stop axes from being overridden.
    
    K = forecast_sigma + 10e-5*eye(size(forecast_sigma))*max(max(forecast_sigma));
    L = chol(K);
 
    sample = forecast_mu + L' * randn(size(forecast_mu));
    plot(xrange, sample, 'Color', colorbrew(2), 'LineWidth', lw);
    sample = forecast_mu + L' * randn(size(forecast_mu));
    plot(xrange, sample, 'Color', colorbrew(3), 'LineWidth', lw);
    sample = forecast_mu + L' * randn(size(forecast_mu));
    plot(xrange, sample, 'Color', colorbrew(4), 'LineWidth', lw);
    xlim([min(xrange), max(xrange)]);
    
    % Make plot prettier.
    set(gcf, 'color', 'white');
    set(gca, 'TickDir', 'out');
    
    % Plot a vertical bar to indicate the start of extrapolation.
    if ~all(forecast_mu == 0) && ~(max(xdata) == max(xrange))  % Don't put extrapolation line on residuals plot.
        y_lim = get(gca,'ylim');
        line( [max(xdata), max(xdata)], y_lim, 'Linestyle', '--', 'Color', [0.3 0.3 0.3 ]);
    end 
    
    % Plot a vertical bar to indicate the start of extrapolation.
    if ~all(forecast_mu == 0) && ~(min(xdata) == min(xrange))  % Don't put extrapolation line on residuals plot.
        y_lim = get(gca,'ylim');
        line( [min(xdata), min(xdata)], y_lim, 'Linestyle', '--', 'Color', [0.3 0.3 0.3 ]);
    end 
    
    set_fig_units_cm( 16,8 );
end


