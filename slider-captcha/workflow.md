https://www.douban.com/

工作流：
1.点击密码登录控件(否则默认是手机激活码)
2.输入账号、密码
3.点击登录控件
4.点击登录控件后出现滑块人机验证，通过滑块控件让待滑动块移动到背景中的目标位置

密码登录控件
<li class="account-tab-account on">密码登录</li>
selector：#app > div > div.account-body-tabs > ul.tab-start > li.account-tab-account.on
xpath：//*[@id="app"]/div/div[1]/ul[1]/li[2]

账号
<input type="text" name="username" class="account-form-input" placeholder="手机号 / 邮箱" value="">
#app > div > div.account-tabcon-start > div.account-form > div:nth-selector：child(3) > div > input
xpath：//*[@id="app"]/div/div[2]/div[1]/div[3]/div/input
输入后：<input type="text" name="username" class="account-form-input" placeholder="手机号 / 邮箱" value="account name">

密码
<input type="password" name="password" class="account-form-input password" placeholder="密码" autocomplete="current-password" value="">
#app > div > div.account-tabcon-start > div.account-form > div:nth-selector：child(4) > div > input
xpath：//*[@id="app"]/div/div[2]/div[1]/div[4]/div/input
输入后：<input type="password" name="password" class="account-form-input password" placeholder="密码" autocomplete="current-password" value="password">

登录控件
<a href="#" class="btn btn-account">登录豆瓣</a>
selector：#app > div > div.account-tabcon-start > div.account-form > div.account-form-field-submit > a
xpath：//*[@id="app"]/div/div[2]/div[1]/div[5]/a


待滑动块(通过滑动控件间接控制)：
<div class="tc-fg-item" aria-label="拖动下方滑块完成拼图" alt="拖动下方滑块完成拼图" style="position: absolute; background-image: url(&quot;https://turing.captcha.qcloud.com/cap_union_new_getcapbysig?img_index=0&amp;image=.....;); background-position: -57.9167px -202.708px; background-size: 282.137px 256.488px; width: 49.6429px; height: 49.6429px; left: 20.6845px; top: 106.318px; z-index: 1; cursor: pointer; opacity: 1;"></div>
selector：#tcOperation > div:nth-child(9)
xpath：//*[@id="tcOperation"]/div[9]

滑动控件：
<div class="tc-fg-item tc-slider-normal" aria-label="拖动下方滑块完成拼图" alt="拖动下方滑块完成拼图" style="left: 18.6161px; top: 166.304px; z-index: 2; width: 53.7798px; height: 28.9583px; line-height: 28.9583px; background-color: rgb(65, 190, 87); box-shadow: rgba(65, 190, 87, 0.5) 0px 0px 4.1369px 0.41369px; cursor: pointer; opacity: 1;"><i class="tc-blank-text">&amp;nbsp;</i><img alt="slider" src="data:image/png;base64,....." class="tc-slider-bg unselectable" style="width: 15.3656px; height: 10.756px;"></div>
selector：#tcOperation > div.tc-fg-item.tc-slider-normal
xpath：//*[@id="tcOperation"]/div[7]

背景：
<div class="tc-bg-img unselectable" id="slideBg" style="position: absolute; background-image: url(&quot;https://turing.captcha.qcloud.com/cap_union_new_getcapbysig?img_index=1&amp;image=.....;); background-position: 0px 0px; background-size: 100%; width: 278px; height: 198.571px; left: 0px; top: 0px; background-repeat: no-repeat; overflow: hidden; z-index: 1; opacity: 1;"></div>
selector：#slideBg
xpath：//*[@id="slideBg"]